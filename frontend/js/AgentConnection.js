/**
 * AgentConnection.js — manages two WebSocket connections to the backend:
 *
 *   /ws/video  — client → server: JPEG frame blobs (screen capture)
 *   /ws/audio  — bidirectional:
 *                  client → server: Int16Array PCM at 16 kHz (mic input)
 *                  server → client: ArrayBuffer PCM at 24 kHz (agent voice)
 *
 * Two sockets are used instead of one to keep video and audio independently
 * testable and to avoid multiplexing complexity in the MVP.
 *
 * React migration note: wrap this class in a useAgentConnection() hook.
 */

export class AgentConnection {
  /**
   * @param {{
   *   videoUrl: string,
   *   audioUrl: string,
   *   onAudio:  (samples: Int16Array) => void,
   *   onClose:  () => void,
   *   onError:  (msg: string) => void,
   * }} options
   */
  constructor({ videoUrl, audioUrl, onAudio, onClose, onError }) {
    this._videoUrl = videoUrl;
    this._audioUrl = audioUrl;
    this._onAudio  = onAudio;
    this._onClose  = onClose;
    this._onError  = onError;

    this._videoSocket     = null;
    this._audioSocket     = null;
    this._intentionalClose = false; // true when WE initiate the close
  }

  /** Opens both WebSocket connections. Resolves when both are open. */
  connect() {
    return Promise.all([
      this._openSocket("video"),
      this._openSocket("audio"),
    ]);
  }

  /** Sends a JPEG frame blob over the video socket. */
  sendFrame(blob) {
    if (this._videoSocket?.readyState === WebSocket.OPEN) {
      this._videoSocket.send(blob);
    }
  }

  /** Sends a PCM chunk (Int16Array) over the audio socket. */
  sendAudio(int16Array) {
    if (this._audioSocket?.readyState === WebSocket.OPEN) {
      this._audioSocket.send(int16Array.buffer);
    }
  }

  /** Closes both sockets cleanly. */
  disconnect() {
    this._intentionalClose = true;
    this._videoSocket?.close();
    this._audioSocket?.close();
    this._videoSocket = null;
    this._audioSocket = null;
  }

  /** @private */
  _openSocket(type) {
    return new Promise((resolve, reject) => {
      const url = type === "video" ? this._videoUrl : this._audioUrl;
      const ws  = new WebSocket(url);

      ws.binaryType = "arraybuffer";

      ws.onopen = () => resolve();

      ws.onmessage = (event) => {
        if (type === "audio" && event.data instanceof ArrayBuffer) {
          // Convert raw 24 kHz int16 PCM from the server into Int16Array
          this._onAudio(new Int16Array(event.data));
        }
      };

      ws.onerror = () => {
        const msg = `WebSocket error on /${type} connection`;
        this._onError(msg);
        reject(new Error(msg));
      };

      ws.onclose = () => {
        // Only surface unexpected closes — not ones we triggered via disconnect()
        if (type === "audio" && !this._intentionalClose) this._onClose();
      };

      if (type === "video") {
        this._videoSocket = ws;
      } else {
        this._audioSocket = ws;
      }
    });
  }
}
