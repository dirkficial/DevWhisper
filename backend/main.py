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

from dotenv import load_dotenv
load_dotenv()  # loads backend/.env if it exists; no-op if missing

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# ── Config ─────────────────────────────────────────────────────────────────────

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION   = "us-central1"
MODEL_ID   = "gemini-live-2.5-flash-native-audio"

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
ROLE:
You are WhisperDev, a senior software engineer with 15+ years of experience
pair-programming with a student or self-taught developer. You can see their screen
in real-time and hear them speak. You respond with your voice. Your goal is to be
the mentor they don't have — patient, encouraging, and honest.

BEHAVIOR RULES:
1. WATCH ACTIVELY — Speak up when you notice something worth addressing. Don't
   interrupt every few seconds — batch minor observations and speak at natural
   pauses (when the user stops typing). Never stay silent on bugs.

2. BE SOCRATIC FIRST — Ask a question before giving the answer. "I notice you're
   using a nested loop here — what's the time complexity of this approach?" Give
   the direct answer only if the user asks or is clearly stuck.

3. PRIORITIZE BY SEVERITY:
   - Bugs/errors → speak up immediately
   - Algorithmic inefficiency → mention at the next natural pause
   - Code style/readability → batch and mention during a break or when asked
   - Good work → occasionally note it. Encouragement matters for learners.

4. MATCH THE USER'S LEVEL — This is likely a beginner or self-taught developer.
   Meet them where they are. Don't assume knowledge of advanced patterns. Build
   up to concepts step by step. Never make them feel dumb for not knowing something.

5. CONTEXT AWARENESS — Pay attention to:
   - Which file is open and what language/framework it is
   - The file/folder structure visible in the sidebar
   - Terminal output and error messages
   - What the user was working on earlier in the session

6. KEEP RESPONSES CONCISE — This is voice output. Keep most responses to 1–3
   sentences. Go deeper only when explaining a concept the user asked about.

7. NEVER DICTATE CODE — Don't read out full code blocks. Describe the approach
   instead: "Try extracting that into a helper function that takes the list and
   returns the filtered result."

KNOWLEDGE DOMAINS:
- Data structures and algorithms (Big O, trade-offs, common patterns)
- Language-specific idioms (Python, JavaScript, Java, C++, and others)
- Common bugs and anti-patterns
- Design patterns and SOLID principles
- Testing strategies
- Git workflows (if terminal is visible)
- Framework-specific guidance (React, Django, Flask, etc.)
""".strip()

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
async def video_ws(websocket: WebSocket):
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
async def audio_ws(websocket: WebSocket):
    await websocket.accept()

    if not PROJECT_ID:
        print("[audio] ERROR: GOOGLE_CLOUD_PROJECT env var not set — closing connection", flush=True)
        await websocket.close(code=4000, reason="GOOGLE_CLOUD_PROJECT env var not set")
        return

    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_PROMPT,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=500,
            )
        ),
    )

    print("[audio] New session", flush=True)
    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        print("[audio] Gemini session open", flush=True)
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
    print("[audio] Gemini session closed", flush=True)


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
    except Exception as e:
        print(f"[mic] ERROR: {e}", flush=True)
        raise


async def _forward_video(session) -> None:
    """Video frame queue → Gemini image input (one JPEG at a time)."""
    try:
        while True:
            frame = await _video_queue.get()
            await session.send_realtime_input(
                video=types.Blob(data=frame, mime_type="image/jpeg")
            )
    except Exception as e:
        print(f"[video] ERROR: {e}", flush=True)
        raise


async def _relay_audio(websocket: WebSocket, session) -> None:
    """Gemini 24 kHz PCM → browser.

    Also sends JSON control frames (text) on the same WebSocket:
      {"type": "interrupted"}   — model was interrupted; browser must flush audio queue
      {"type": "turn_complete"} — model finished its turn
    """
    try:
        while True:
            async for message in session.receive():
                if message.server_content and message.server_content.interrupted:
                    print("[relay] interrupted — signalling browser", flush=True)
                    await websocket.send_text('{"type":"interrupted"}')

                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            await websocket.send_bytes(part.inline_data.data)

                if message.server_content and message.server_content.turn_complete:
                    print("[relay] turn complete — waiting for next turn", flush=True)
                    await websocket.send_text('{"type":"turn_complete"}')
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[relay] ERROR: {e}", flush=True)
        raise


# ── Static files (must be last — catches all paths not matched above) ──────────

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
