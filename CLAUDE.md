# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DevWhisper** (agent persona: *WhisperDev*) is an AI pair programmer that watches a developer's IDE via real-time screen capture, listens through the microphone, and responds with voice — proactively catching bugs, asking Socratic questions, and explaining concepts. It uses the Gemini Live API for bidirectional audio + vision streaming.

## Architecture

```
Browser (frontend/)
  ├── getDisplayMedia()  → JPEG frames @ ~1 fps  ─┐
  └── getUserMedia()     → PCM audio @ 16 kHz    ─┤─ WebSocket ─► FastAPI Backend (backend/)
                                                   │                   │
                         PCM audio @ 24 kHz  ◄────┘         Gemini Live API
                         (agent voice)                    (gemini-live-2.5-flash-native-audio)
```

**Frontend** — Plain HTML/JS (`frontend/`). No build step. Organized into 4 classes in `app.js`: `ScreenCapture`, `MicCapture`, `AgentConnection`, `AudioPlayer`. Two WebSocket connections: `/ws/video` (client→server JPEG) and `/ws/audio` (bidirectional PCM).

**Backend** — Python + FastAPI (`backend/`). Bridges the browser WebSocket to the Gemini Live API session. Forwards JPEG frames as vision input and PCM audio as `send_realtime_input`. Receives agent audio and relays back to browser.

**AI Model** — `gemini-live-2.5-flash-native-audio` via Vertex AI. Voice: Aoede. Audio in: 16 kHz PCM. Audio out: 24 kHz PCM.

## Authentication

Uses **Vertex AI** (not AI Studio). Requires Google Cloud ADC:

```bash
gcloud auth application-default login
```

Set the project ID in code or via env var:
```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

## Running the Day 1 POC

```bash
# Install dependency
/Library/Frameworks/Python.framework/Versions/3.12/bin/pip3 install -U google-genai

# Run (always use the explicit Python path to avoid env mismatch)
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 live_test.py

# Play the output audio (24 kHz, 16-bit, mono raw PCM)
ffplay -f s16le -ar 24000 -ac 1 senpaidev_response.pcm
```

## Running the Mock WebSocket Server (Day 2)

```bash
pip3 install websockets

# Terminal 1 — WebSocket mock server
python3 ws_mock_server.py

# Terminal 2 — static file server (required: AudioWorklet needs HTTP, not file://)
python3 -m http.server 3000 --directory frontend/
```

Then open `http://localhost:3000` in Chrome.
WebSocket connects to `ws://localhost:8000` (configured at the top of `js/app.js`).

## Running the Backend (Day 3+)

```bash
cd backend
pip3 install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Key Technical Constraints

- **Mic audio to Gemini:** must be `audio/pcm;rate=16000` — the `pcm-processor.js` AudioWorklet handles downsampling from the browser's native rate.
- **Agent audio from Gemini:** 24 kHz, 16-bit, mono PCM (no file header).
- **Frame rate:** 1 fps is sufficient for code review; higher rates waste bandwidth with little gain.
- **Model requires Vertex AI:** `gemini-live-2.5-flash-native-audio` is only available through the Vertex AI endpoint, not AI Studio.
- **`turn_complete` signal:** the `async for message in session.receive()` loop **must** break on `message.server_content.turn_complete` — otherwise it hangs indefinitely after the agent finishes speaking.

## System Prompt

The agent persona (WhisperDev) is defined as a `system_instruction` in `LiveConnectConfig`. Key behaviors: proactive watching (speak at natural pauses, not every 5 seconds), Socratic-first (ask before answering), severity-based prioritization (bugs immediately, style later), concise voice responses (1–3 sentences).

## Build Schedule Reference

- Day 1 ✅ — Gemini Live API POC (`live_test.py`)
- Day 2 — Frontend screen + mic capture (`frontend/`)
- Day 3 — FastAPI backend + full pipeline (`backend/`)
- Day 4 — System prompt tuning + Firestore logging
- Day 5 — Docker + Cloud Run deployment
- Day 6 — Demo video
- Day 7 — Submit
