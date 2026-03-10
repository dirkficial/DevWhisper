# DevWhisper — Engineer Onboarding Guide

This document explains what DevWhisper is, how it's structured, how to run it, and how each piece works. Read this top-to-bottom before touching any code.

---

## What Is DevWhisper?

DevWhisper is an AI pair programmer that:

1. **Watches your screen** — captures your IDE via `getDisplayMedia()` (browser screen sharing), sends JPEG frames to the backend
2. **Listens to your mic** — captures your voice via `getUserMedia()`, streams 16 kHz PCM audio to the backend
3. **Talks back to you** — receives 24 kHz PCM audio from Gemini (the AI model) and plays it through your speakers in real time

The AI persona is called **WhisperDev**. It proactively notices bugs, asks Socratic questions, and explains what it sees — like a senior engineer sitting next to you. It uses Google's **Gemini Live API** (specifically `gemini-live-2.5-flash-native-audio`) for bidirectional audio + vision streaming.

---

## High-Level Architecture

```
Browser (frontend/)
  ├── getDisplayMedia()  →  JPEG frames @ ~1 fps   ─┐
  └── getUserMedia()     →  PCM audio @ 16 kHz     ─┤─ WebSocket ─► FastAPI Backend (backend/)
                                                     │                      │
                         PCM audio @ 24 kHz  ◄───────┘            Gemini Live API
                         (agent voice)                    (gemini-live-2.5-flash-native-audio)
```

There are **two WebSocket connections** from the browser to the backend:

| WebSocket endpoint | Direction | Payload |
|---|---|---|
| `/ws/video?mode=<mode>` | client → server | JPEG blobs (screen frames) |
| `/ws/audio?mode=<mode>` | bidirectional | client→server: 16 kHz PCM; server→client: 24 kHz PCM |

The backend owns a single Gemini Live session per audio connection and bridges all three streams through it.

---

## Project File Structure

```
DevWhisper/
├── backend/
│   ├── main.py              # FastAPI server — the entire backend
│   └── requirements.txt     # Python dependencies
│
├── frontend/
│   ├── index.html           # The whole UI (one page, no build step)
│   ├── css/
│   │   └── styles.css       # All styles
│   └── js/
│       ├── app.js           # Entry point — wires everything together
│       ├── ui.js            # DOM helpers (log panel, status badge)
│       ├── ScreenCapture.js # getDisplayMedia → JPEG frame loop
│       ├── MicCapture.js    # getUserMedia → AudioWorklet → PCM chunks
│       ├── AgentConnection.js # Two WebSocket connections to backend
│       ├── AudioPlayer.js   # Plays back 24 kHz PCM from the agent
│       └── pcm-processor.js # AudioWorklet: downsample + convert to int16
│
├── live_test.py             # Day 1 POC — raw Gemini API test (no server)
├── ws_mock_server.py        # Day 2 mock server — validates frontend without Gemini
│
└── tests/
    ├── browser/             # Browser-side JS tests
    │   ├── test.html
    │   └── test-audio.js
    └── python/              # pytest suite
        ├── conftest.py
        ├── test_live_api.py
        └── test_ws_server.py
```

---

## Prerequisites

### Python

```bash
# The project uses Python 3.12 at this explicit path (avoids env mismatch on macOS)
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --version
```

### Google Cloud Auth

The Gemini model is hosted on **Vertex AI** (not the public AI Studio API). You must authenticate with Google Cloud:

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
```

Your GCP project must have the **Vertex AI API** enabled.

---

## How to Run It

### Option A — Full Stack (backend + real Gemini AI)

This is the real deal. The backend connects to Gemini Live.

```bash
# 1. Install Python dependencies
cd backend
pip3 install -r requirements.txt

# 2. Set your GCP project
export GOOGLE_CLOUD_PROJECT="your-project-id"

# 3. Start the backend (serves frontend too via StaticFiles)
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` in Chrome.

> **Why Chrome?** `getDisplayMedia()` and `AudioWorklet` work best there. Firefox may work but is untested.

### Option B — Mock Server (frontend validation without Gemini)

Use this during Day 2-style frontend work when you don't need real AI responses.

```bash
# Terminal 1 — mock WebSocket server
python3 ws_mock_server.py

# Terminal 2 — static file server (AudioWorklet REQUIRES HTTP, not file://)
python3 -m http.server 3000 --directory frontend/
```

Open `http://localhost:3000` in Chrome.

The mock server logs incoming video frames and audio chunks, and echoes silent audio back so the `AudioPlayer` gets exercised.

### Option C — Raw Gemini API POC

`live_test.py` was the Day 1 proof of concept. It sends a screenshot + text prompt directly to Gemini Live and saves the audio response as a `.pcm` file. No browser or server involved.

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 live_test.py

# Play the response
ffplay -f s16le -ar 24000 -ac 1 WhisperDev_response.pcm
```

---

## Deep Dive: How Each Piece Works

### Frontend

#### `index.html`

The entire UI is a single HTML file. It has:
- A **mode selector** (radio buttons): Proactive vs. Reactive
- **Start / Stop buttons**
- A **session log panel** that shows timestamped events
- A hidden `<video>` element that `ScreenCapture` draws from

There is no build step, no bundler, no npm. It's plain ES modules loaded with `<script type="module">`.

#### `app.js` — Entry Point

This is the glue. When the user clicks **Start**:

1. Creates an `AudioPlayer` instance first (so it's ready before any audio arrives)
2. Creates `AgentConnection` and calls `.connect()` — opens both WebSockets
3. Creates `ScreenCapture` and calls `.start()` — begins sending 1 fps JPEG frames
4. Creates `MicCapture` and calls `.start()` — begins streaming 16 kHz PCM audio

When the user clicks **Stop** (or the server closes), `stopSession()` tears everything down cleanly.

The WebSocket URL is derived from the current page origin:
```js
const WS_BASE = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;
```
This means the same code works locally at `ws://localhost:8000` and on Cloud Run at `wss://your-app.run.app` — no hardcoded URLs.

#### `ScreenCapture.js`

Calls `navigator.mediaDevices.getDisplayMedia()` to request screen share permission. Then every 1000ms:
- Draws the current video frame onto an offscreen `<canvas>`
- Calls `canvas.toBlob()` at JPEG quality 0.8
- Passes the blob to `AgentConnection.sendFrame()`

1 fps is intentional. Code on a screen doesn't change fast enough to need more, and higher rates waste bandwidth.

#### `MicCapture.js` + `pcm-processor.js`

This is the trickiest part. The browser's `AudioContext` always runs at the device's native sample rate (44100 Hz or 48000 Hz — you can't choose). Gemini requires exactly **16000 Hz**. Solution: an **AudioWorklet**.

Flow:
1. `getUserMedia()` opens the mic → gives you a `MediaStream`
2. `AudioContext` is created at the device's native rate
3. `pcm-processor.js` is loaded as an AudioWorklet module — it runs in a separate thread
4. The mic stream is connected to the worklet node
5. The worklet's `process()` method receives float32 audio at native rate, **downsamples to 16 kHz via linear interpolation**, converts to int16, and posts the chunk to the main thread via `this.port.postMessage()`
6. The main thread receives chunks in `onmessage` and calls `AgentConnection.sendAudio()`

Why AudioWorklet and not `ScriptProcessorNode`? `ScriptProcessorNode` is deprecated and runs on the main thread, causing glitches. AudioWorklet runs in a dedicated audio thread.

Why `pcm-processor.js` must be a separate file: AudioWorklet scripts have their own global scope (`AudioWorkletGlobalScope`) — they can't be inlined or bundled.

#### `AgentConnection.js`

Manages two WebSocket connections. Key design decisions:
- `ws.binaryType = "arraybuffer"` — required to receive binary data as `ArrayBuffer` (not `Blob`)
- Video socket is send-only (the `onmessage` handler does nothing for video)
- Audio socket receives `ArrayBuffer` → wraps in `Int16Array` → calls `onAudio` callback
- `_intentionalClose` flag prevents the `onClose` callback from firing when WE close the connection (vs. the server closing it unexpectedly)

#### `AudioPlayer.js`

Plays back 24 kHz int16 PCM chunks using the Web Audio API.

The challenge: Gemini sends audio in many small chunks over time. If you create an `AudioBufferSourceNode` for each chunk and `.start()` them all at `currentTime`, they overlap or have gaps. The solution is **back-to-back scheduling**:

```js
const startAt = Math.max(this._ctx.currentTime, this._nextPlayTime);
source.start(startAt);
this._nextPlayTime = startAt + buffer.duration;
```

Each chunk is scheduled to start exactly when the previous one ends. This gives seamless, click-free playback.

The `AudioContext` is created lazily on the first `play()` call to comply with browser autoplay policies (browsers block audio that starts without a user gesture).

---

### Backend

#### `backend/main.py`

The entire backend is one file. It uses FastAPI and serves both the WebSocket endpoints and the frontend static files.

**Key components:**

**`_video_queue`** — An `asyncio.Queue(maxsize=5)` that decouples the video WebSocket from the Gemini session. The video handler puts frames in; the Gemini pipeline pulls them out. If the queue is full (Gemini is slow), the oldest frame is dropped — we always want near-realtime frames, not a backlog.

**`video_ws` endpoint** (`/ws/video`) — Accepts the browser connection, then loops forever pulling JPEG blobs and putting them in `_video_queue`. That's it.

**`audio_ws` endpoint** (`/ws/audio`) — This one owns the Gemini session lifecycle:
1. Checks `GOOGLE_CLOUD_PROJECT` env var (fails with close code 4000 if missing)
2. Creates a `genai.Client` using Vertex AI
3. Builds a `LiveConnectConfig` with the system prompt (based on the `mode` query param) and voice settings
4. Opens a Gemini Live session with `async with client.aio.live.connect(...) as session`
5. Launches three concurrent async tasks (see below)
6. Waits for any one task to finish (`asyncio.FIRST_COMPLETED`), then cancels the rest

**Three pipeline tasks:**

| Task | What it does |
|---|---|
| `_forward_mic` | Reads raw PCM bytes from the browser WebSocket, wraps in `types.Blob(mime_type="audio/pcm;rate=16000")`, calls `session.send_realtime_input(audio=...)` |
| `_forward_video` | Pulls JPEG bytes from `_video_queue`, wraps in `types.Blob(mime_type="image/jpeg")`, calls `session.send_realtime_input(video=...)` |
| `_relay_audio` | Iterates `session.receive()`, extracts PCM bytes from `message.server_content.model_turn.parts`, sends raw bytes to the browser audio WebSocket |

**Error handling:** Each task catches `WebSocketDisconnect` to exit cleanly (that's expected when the user stops). Any other exception is printed with a `[mic] ERROR`, `[video] ERROR`, or `[relay] ERROR` prefix and re-raised — this causes `asyncio.wait()` to pick it up as a completed task and the whole pipeline tears down.

**Static file serving:** The last line mounts the `frontend/` directory at `/`. This is why the backend serves the UI at `http://localhost:8000` — you don't need a separate file server in production.

**System prompts:**

There are two modes, both sharing the base WhisperDev persona:
- **Proactive** — speaks up unprompted when it spots bugs, errors, or confusion. Silent during routine typing.
- **Reactive** — completely silent until the developer speaks directly to it.

The mode is passed as a `?mode=proactive` query param on the WebSocket URL and used to pick the system prompt.

---

## Audio Format Reference

| Stream | Direction | Format |
|---|---|---|
| Mic input | Browser → Backend → Gemini | 16 kHz, 16-bit signed int, mono PCM (`audio/pcm;rate=16000`) |
| Agent output | Gemini → Backend → Browser | 24 kHz, 16-bit signed int, mono PCM (raw bytes, no file header) |

These are not negotiable — the Gemini Live API requires exactly these formats. The `pcm-processor.js` worklet handles the browser's native rate → 16 kHz conversion. The `AudioPlayer` creates its `AudioContext` at exactly 24000 Hz to match the output.

---

## Development Tips

### Diagnosing audio silence

If WhisperDev connects but never responds, check the uvicorn terminal. You should see:

```
[audio] New session — mode=proactive
[audio] Gemini session open
```

If you see `[mic] ERROR: ...` or `[relay] ERROR: ...`, that's where to look. Common causes:
- Auth failed (check `GOOGLE_CLOUD_PROJECT` and `gcloud auth application-default login`)
- Wrong audio format (shouldn't happen if you haven't changed `pcm-processor.js`)
- Gemini API quota exceeded

### AudioWorklet requires HTTP

You cannot open `frontend/index.html` directly from the filesystem (`file://` URLs). `AudioWorklet.addModule()` is blocked on `file://` origins. Always serve via a local HTTP server.

### One session at a time

The current implementation has a **single global `_video_queue`**. If two browsers connect simultaneously, they share one queue and fight over frames. This is intentional for the MVP — multi-session support is a future concern.

### The `turn_complete` signal

In `live_test.py` (the POC), the receive loop breaks on `turn_complete` because the script does a single question-answer cycle. In the real backend (`_relay_audio`), we do **not** break on `turn_complete` — the session stays open indefinitely for multiple conversation turns. If you ever see `[relay] session.receive() ended normally`, it means Gemini closed the session from its side, which is unexpected during normal use.

---

## What's Next (Build Schedule)

| Day | Status | Work |
|---|---|---|
| 1 | Done | Gemini Live API POC (`live_test.py`) |
| 2 | Done | Frontend screen + mic capture (`frontend/`) |
| 3 | Done | FastAPI backend + full pipeline (`backend/`) |
| 4 | Up next | System prompt tuning + Firestore logging |
| 5 | | Docker + Cloud Run deployment |
| 6 | | Demo video |
| 7 | | Submit |
