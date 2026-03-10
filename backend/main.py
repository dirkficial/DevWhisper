"""
main.py — DevWhisper FastAPI backend.

Bridges two browser WebSocket connections to a single Gemini Live API session:
  /ws/video?mode=<proactive|reactive>  — client→server: JPEG frames (screen capture)
  /ws/audio?mode=<proactive|reactive>  — bidirectional:
      client→server: 16 kHz PCM (mic input)
      server→client: 24 kHz PCM (agent voice)

The audio WebSocket owns the Gemini session lifecycle.
The video WebSocket feeds frames into a shared queue that the audio handler drains.

Usage:
    export GOOGLE_CLOUD_PROJECT=your-project-id
    uvicorn main:app --reload --port 8000
"""

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# ── Config ─────────────────────────────────────────────────────────────────────

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION   = "us-central1"
MODEL_ID   = "gemini-live-2.5-flash-native-audio"

# ── System prompts ─────────────────────────────────────────────────────────────

_SHARED_PERSONA = """
You are WhisperDev, an expert AI pair programmer embedded in a developer's workflow.
You can see their entire screen in real time and hear them as they work.

Your personality: Direct, knowledgeable, and encouraging — like a senior engineer
sitting beside the developer. Keep all responses to 1–3 sentences. You are speaking
aloud, not writing documentation. Never read out code verbatim — describe changes
in plain language instead.
""".strip()

SYSTEM_PROMPTS = {
    "proactive": _SHARED_PERSONA + """

Proactive mode: Speak up without being asked when you notice:
- Bugs or logic errors → always mention immediately
- Security vulnerabilities → always mention immediately
- Performance problems worth addressing now
- A moment where the developer seems stuck or confused

Stay silent during routine typing. Speak at natural pauses, not every few seconds.
Ask a Socratic question first when the developer appears to be in the middle of
figuring something out. Give a direct answer when they are clearly stuck.
""".strip(),

    "reactive": _SHARED_PERSONA + """

Reactive mode: Stay completely silent until the developer speaks to you directly.
When they do, respond concisely. Reference what you can see on the screen when
relevant. Do not volunteer observations or commentary unprompted.
""".strip(),
}

# ── Shared state (single-session MVP) ─────────────────────────────────────────
#
# One active Gemini session at a time. The video handler drops frames into
# _video_queue; the audio handler drains it and forwards to Gemini.
# maxsize=5 keeps the queue small so frames are always near-realtime.

_video_queue: asyncio.Queue = asyncio.Queue(maxsize=5)

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="DevWhisper")


# ── WebSocket: /ws/video ───────────────────────────────────────────────────────

@app.websocket("/ws/video")
async def video_ws(
    websocket: WebSocket,
    mode: str = Query("proactive"),  # accepted but unused here; audio owns the session
):
    await websocket.accept()
    try:
        async for data in websocket.iter_bytes():
            # Drop the oldest frame if the queue is full — a slow Gemini call
            # should never cause mic audio to back up.
            if _video_queue.full():
                try:
                    _video_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await _video_queue.put(data)
    except WebSocketDisconnect:
        pass


# ── WebSocket: /ws/audio ───────────────────────────────────────────────────────

@app.websocket("/ws/audio")
async def audio_ws(
    websocket: WebSocket,
    mode: str = Query("proactive"),
):
    await websocket.accept()

    if not PROJECT_ID:
        await websocket.close(code=4000, reason="GOOGLE_CLOUD_PROJECT env var not set")
        return

    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

    system_instruction = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["proactive"])

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system_instruction,
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
        ),
    )

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        tasks = [
            asyncio.create_task(_forward_mic(websocket, session)),
            asyncio.create_task(_forward_video(session)),
            asyncio.create_task(_relay_audio(websocket, session)),
        ]
        # Run until any task finishes (e.g. browser disconnects) then cancel the rest.
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


# ── Pipeline tasks ─────────────────────────────────────────────────────────────

async def _forward_mic(websocket: WebSocket, session) -> None:
    """Browser 16 kHz PCM → Gemini audio input."""
    try:
        async for data in websocket.iter_bytes():
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
            )
    except WebSocketDisconnect:
        pass


async def _forward_video(session) -> None:
    """Video frame queue → Gemini image input (one JPEG at a time)."""
    while True:
        frame = await _video_queue.get()
        await session.send_realtime_input(
            video=types.Blob(data=frame, mime_type="image/jpeg")
        )


async def _relay_audio(websocket: WebSocket, session) -> None:
    """Gemini 24 kHz PCM → browser.

    Does NOT break on turn_complete — the session stays open for the full
    duration of the developer's work session (multiple turns expected).
    """
    try:
        async for message in session.receive():
            if message.server_content and message.server_content.model_turn:
                for part in message.server_content.model_turn.parts:
                    if part.inline_data:
                        await websocket.send_bytes(part.inline_data.data)
    except WebSocketDisconnect:
        pass


# ── Static files (must be last — catches all paths not matched above) ──────────

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
