/**
 * app.js — entry point.
 *
 * Wires together ScreenCapture, MicCapture, AgentConnection, and AudioPlayer.
 * Handles the Start/Stop button lifecycle and surfaces errors to the UI log.
 */

import { ScreenCapture }    from "./ScreenCapture.js";
import { MicCapture }       from "./MicCapture.js";
import { AgentConnection }  from "./AgentConnection.js";
import { AudioPlayer }      from "./AudioPlayer.js";
import { startBtn, stopBtn, log, setStatus } from "./ui.js";

// ─── Configuration ────────────────────────────────────────────────────────────
// Derives the WebSocket base from the current page origin so the same code
// works locally (ws://localhost:8000) and on Cloud Run (wss://...).
const WS_BASE = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;

const modeSelector = document.getElementById("modeSelector");

// ─── Module-level instances ───────────────────────────────────────────────────
// Instantiated fresh on each Start so resources are clean.
let screenCapture   = null;
let micCapture      = null;
let agentConnection = null;
let audioPlayer     = null;

// ─── Start ────────────────────────────────────────────────────────────────────
startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  modeSelector.classList.add("disabled");
  setStatus("connecting");
  log("Starting session…", "info");

  // Read the selected mode and build URLs with the query param
  const mode = document.querySelector("input[name='mode']:checked").value;
  const videoUrl = `${WS_BASE}/ws/video?mode=${mode}`;
  const audioUrl = `${WS_BASE}/ws/audio?mode=${mode}`;
  log(`Mode: ${mode}`, "info");

  try {
    // 1. AudioPlayer must exist before AgentConnection so onAudio never fires on null
    audioPlayer = new AudioPlayer();

    // 2. Connect WebSockets — fail fast if the server is down
    agentConnection = new AgentConnection({
      videoUrl,
      audioUrl,
      onAudio:  (int16Array) => audioPlayer.play(int16Array),
      onClose:  () => { log("Server closed the connection.", "warn"); stopSession(); },
      onError:  (msg) => log(msg, "err"),
    });

    await agentConnection.connect();
    log("Connected to server.", "ok");

    // 3. Start screen capture
    screenCapture = new ScreenCapture({
      onFrame: (blob) => {
        agentConnection.sendFrame(blob);
        log(`Frame sent — ${(blob.size / 1024).toFixed(1)} KB`);
      },
      onStop: () => {
        log("Screen sharing ended.", "warn");
        stopSession();
      },
    });
    await screenCapture.start();
    log("Screen capture started.", "ok");

    // 4. Start mic capture
    micCapture = new MicCapture({
      onChunk: (int16Array) => {
        agentConnection.sendAudio(int16Array);
      },
    });
    await micCapture.start();
    log("Microphone capture started.", "ok");

    setStatus("streaming");
    stopBtn.disabled = false;

  } catch (err) {
    log(`Failed to start: ${err.message}`, "err");
    setStatus("error");
    stopSession();
    startBtn.disabled = false;
  }
});

// ─── Stop ─────────────────────────────────────────────────────────────────────
stopBtn.addEventListener("click", () => {
  stopSession();
  log("Session stopped.", "warn");
});

function stopSession() {
  screenCapture?.stop();
  micCapture?.stop();
  agentConnection?.disconnect();
  audioPlayer?.stop();

  screenCapture   = null;
  micCapture      = null;
  agentConnection = null;
  audioPlayer     = null;

  setStatus("stopped");
  stopBtn.disabled  = true;
  startBtn.disabled = false;
  modeSelector.classList.remove("disabled");
}
