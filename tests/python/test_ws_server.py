"""
test_ws_server.py — Tests for ws_mock_server.py

What these catch:
  - Endpoint routing is wrong (video/audio handlers swapped or missing)
  - Audio silent-chunk response is missing or wrong size
  - Server crashes on rapid or concurrent connections
  - Unknown paths aren't rejected cleanly

Run:
    python3 -m pytest tests/python/test_ws_server.py -v
"""

import asyncio
import sys
import os

import pytest
import websockets
import websockets.exceptions

# Make the project root importable regardless of where pytest is invoked from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from ws_mock_server import handler, SILENT_CHUNK

# Use a port that won't conflict with the running dev server (8000)
TEST_PORT = 8765
TEST_URL  = f"ws://localhost:{TEST_PORT}"


@pytest.fixture
async def server():
    """Starts a fresh server instance for each test, then shuts it down."""
    async with websockets.serve(handler, "localhost", TEST_PORT):
        yield


# ─── SILENT_CHUNK unit test (no network needed) ───────────────────────────────

def test_silent_chunk_is_correct_format():
    """
    100 ms of silence at 24 kHz, 16-bit, mono = 2400 samples × 2 bytes = 4800 bytes.
    If this is wrong, AudioPlayer will receive misaligned PCM and produce noise/clicks.
    """
    assert len(SILENT_CHUNK) == 4800, (
        f"Expected 4800 bytes (100ms @ 24kHz 16-bit mono), got {len(SILENT_CHUNK)}"
    )
    assert all(b == 0 for b in SILENT_CHUNK), "Silent chunk should be all zero bytes"


# ─── Video endpoint ───────────────────────────────────────────────────────────

async def test_video_endpoint_accepts_connection(server):
    """Basic connectivity check for /ws/video."""
    async with websockets.connect(f"{TEST_URL}/ws/video"):
        pass  # connection opened and closed cleanly


async def test_video_endpoint_receives_frame(server):
    """
    Server should accept binary data on /ws/video without error.
    It doesn't send a response — if it did, recv() would time out here.
    """
    async with websockets.connect(f"{TEST_URL}/ws/video") as ws:
        fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 5000  # JPEG magic bytes + padding
        await ws.send(fake_jpeg)
        # Server should not send anything back for video frames
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), timeout=0.3)


async def test_video_endpoint_handles_multiple_frames(server):
    """
    Simulates 1 fps capture over 5 seconds. If the server errors after
    the first frame, this will raise on the second send.
    """
    async with websockets.connect(f"{TEST_URL}/ws/video") as ws:
        for i in range(5):
            await ws.send(b"frame-data" * 500)  # ~5 KB per frame
        # All 5 frames accepted without error


# ─── Audio endpoint ───────────────────────────────────────────────────────────

async def test_audio_endpoint_accepts_connection(server):
    """Basic connectivity check for /ws/audio."""
    async with websockets.connect(f"{TEST_URL}/ws/audio"):
        pass


async def test_audio_endpoint_echoes_silent_chunk(server):
    """
    Every audio chunk sent to the server should be echoed back as SILENT_CHUNK.
    This is what exercises AudioPlayer in the browser during Day 2 testing.
    If this fails, the browser will never play any audio back.
    """
    async with websockets.connect(f"{TEST_URL}/ws/audio") as ws:
        pcm_chunk = bytes(512)  # 256 samples of silence at 16kHz
        await ws.send(pcm_chunk)
        response = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert response == SILENT_CHUNK, (
            f"Expected SILENT_CHUNK ({len(SILENT_CHUNK)} bytes), "
            f"got {len(response)} bytes"
        )


async def test_audio_endpoint_responds_to_multiple_chunks(server):
    """
    Each chunk should get exactly one SILENT_CHUNK back.
    Tests that the server doesn't batch, drop, or duplicate responses.
    """
    async with websockets.connect(f"{TEST_URL}/ws/audio") as ws:
        for _ in range(3):
            await ws.send(bytes(256))
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert response == SILENT_CHUNK


# ─── Unknown path ─────────────────────────────────────────────────────────────

async def test_unknown_path_is_rejected(server):
    """
    Any path other than /ws/video or /ws/audio should be closed with code 4004.
    If this is missing, a misconfigured frontend would silently appear connected.
    """
    with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
        async with websockets.connect(f"{TEST_URL}/ws/unknown") as ws:
            await ws.recv()  # trigger the receive so the close propagates

    assert exc_info.value.rcvd.code == 4004, (
        f"Expected close code 4004, got {exc_info.value.rcvd.code}"
    )


# ─── Concurrent connections ───────────────────────────────────────────────────

async def test_simultaneous_video_and_audio(server):
    """
    The real app opens both sockets at the same time via Promise.all().
    Verifies the server handles concurrent connections without interference.
    """
    async with websockets.connect(f"{TEST_URL}/ws/video") as video_ws:
        async with websockets.connect(f"{TEST_URL}/ws/audio") as audio_ws:
            # Send on both simultaneously
            await asyncio.gather(
                video_ws.send(b"jpeg-frame" * 200),
                audio_ws.send(bytes(256)),
            )
            # Audio should still respond correctly under concurrent load
            response = await asyncio.wait_for(audio_ws.recv(), timeout=2.0)
            assert response == SILENT_CHUNK
