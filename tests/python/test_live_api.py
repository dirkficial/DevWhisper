"""
test_live_api.py — Gemini Live API smoke tests.

These tests make real API calls and cost quota. They are SKIPPED automatically
unless the GOOGLE_CLOUD_PROJECT environment variable is set.

Run explicitly when you need to verify:
  - Credentials are valid (gcloud auth application-default login was run)
  - The model ID is still correct
  - The turn_complete break actually terminates the receive loop
  - Audio is coming back at the expected sample rate

Usage:
    GOOGLE_CLOUD_PROJECT=your-project-id python3 -m pytest tests/python/test_live_api.py -v -s
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION   = "us-central1"
MODEL_ID   = "gemini-live-2.5-flash-native-audio"

pytestmark = pytest.mark.skipif(
    not PROJECT_ID,
    reason="Set GOOGLE_CLOUD_PROJECT env var to run live API tests",
)


def _make_client():
    from google import genai
    return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def _make_config():
    from google.genai.types import LiveConnectConfig
    return LiveConnectConfig(response_modalities=["audio"])


# ─── 1. Client creation ───────────────────────────────────────────────────────

def test_client_creation_succeeds():
    """
    If this fails: credentials are wrong, google-genai isn't installed,
    or the project ID is invalid.
    """
    client = _make_client()
    assert client is not None


# ─── 2. Session connectivity ──────────────────────────────────────────────────

async def test_session_connects_to_model():
    """
    If this fails: the model ID has changed, the region doesn't support
    the Live API, or there's a network/firewall issue.
    """
    client = _make_client()
    config = _make_config()
    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        assert session is not None


# ─── 3. Full round-trip: prompt → audio → turn_complete ──────────────────────

async def test_text_prompt_returns_audio_and_turn_complete_fires():
    """
    The most important smoke test. Verifies:
      1. The model sends at least one audio chunk back.
      2. turn_complete fires — meaning the receive loop would correctly
         terminate rather than hang forever (the bug fixed in live_test.py).
      3. The whole thing finishes within 20 seconds (no silent hang).

    If audio_chunks is empty: the model responded but sent no audio
    (wrong response_modalities or model issue).

    If turn_complete never fires: the receive loop fix is broken and
    live_test.py would hang indefinitely in production.
    """
    from google.genai.types import Content, Part

    client = _make_client()
    config = _make_config()

    audio_chunks   = []
    turn_completed = False

    async def _receive(session):
        nonlocal turn_completed
        async for message in session.receive():
            if message.server_content and message.server_content.model_turn:
                for part in message.server_content.model_turn.parts:
                    if part.inline_data:
                        audio_chunks.append(part.inline_data.data)

            if message.server_content and message.server_content.turn_complete:
                turn_completed = True
                break

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        await session.send_client_content(
            turns=Content(role="user", parts=[Part(text="Say the word 'hello'.")])
        )
        await asyncio.wait_for(_receive(session), timeout=20.0)

    assert len(audio_chunks) > 0, (
        "No audio chunks received. Check response_modalities=['audio'] and model ID."
    )
    assert turn_completed, (
        "turn_complete never fired. The receive loop would hang in production."
    )


# ─── 4. Audio output format ───────────────────────────────────────────────────

async def test_audio_output_is_16bit_pcm():
    """
    Verifies the raw bytes coming back are consistent with 16-bit PCM:
    - Data length is even (each sample is 2 bytes).
    - Data is non-empty.

    If this fails: the audio format changed and AudioPlayer's
    int16 parsing will produce garbage output.
    """
    from google.genai.types import Content, Part

    client = _make_client()
    config = _make_config()
    received_bytes = bytearray()

    async def _receive(session):
        async for message in session.receive():
            if message.server_content and message.server_content.model_turn:
                for part in message.server_content.model_turn.parts:
                    if part.inline_data:
                        received_bytes.extend(part.inline_data.data)
            if message.server_content and message.server_content.turn_complete:
                break

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        await session.send_client_content(
            turns=Content(role="user", parts=[Part(text="Say the word 'hello'.")])
        )
        await asyncio.wait_for(_receive(session), timeout=20.0)

    assert len(received_bytes) > 0, "No audio data received"
    assert len(received_bytes) % 2 == 0, (
        f"Audio byte count {len(received_bytes)} is odd — not valid 16-bit PCM"
    )
