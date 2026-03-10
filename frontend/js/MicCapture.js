/**
 * MicCapture.js — captures the microphone and emits Int16Array PCM chunks
 * at 16 kHz via a callback, ready for the Gemini Live API.
 *
 * React migration note: wrap this class in a useMicCapture() hook.
 */

// Path is relative to index.html (the page origin), not this JS file.
const WORKLET_URL = "js/pcm-processor.js";

export class MicCapture {
  /**
   * @param {{ onChunk: (samples: Int16Array) => void }} options
   */
  constructor({ onChunk }) {
    this._onChunk      = onChunk;
    this._stream       = null;
    this._audioContext = null;
    this._sourceNode   = null;
    this._workletNode  = null;
  }

  /**
   * Requests microphone permission, loads the AudioWorklet, and starts streaming.
   * Throws if permission is denied or the worklet fails to load.
   */
  async start() {
    this._stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

    this._audioContext = new AudioContext();

    await this._audioContext.audioWorklet.addModule(WORKLET_URL);

    this._sourceNode  = this._audioContext.createMediaStreamSource(this._stream);
    this._workletNode = new AudioWorkletNode(this._audioContext, "pcm-processor");

    // Receive downsampled Int16Array chunks from the worklet
    this._workletNode.port.onmessage = (event) => this._onChunk(event.data);

    // Connect: mic source → worklet (worklet doesn't need an output destination)
    this._sourceNode.connect(this._workletNode);
  }

  /** Stops mic capture and releases all audio resources. */
  stop() {
    this._sourceNode?.disconnect();
    this._workletNode?.disconnect();

    if (this._stream) {
      this._stream.getTracks().forEach((t) => t.stop());
      this._stream = null;
    }

    if (this._audioContext) {
      this._audioContext.close();
      this._audioContext = null;
    }
  }
}
