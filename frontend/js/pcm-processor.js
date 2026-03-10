/**
 * pcm-processor.js — AudioWorkletProcessor
 *
 * Loaded by MicCapture via audioContext.audioWorklet.addModule().
 * This file MUST be separate — AudioWorklet scripts run in their own global scope
 * and cannot be inlined or bundled with the main thread code.
 *
 * What it does:
 *   1. Receives float32 audio from the browser at the device's native sample rate
 *      (commonly 44100 or 48000 Hz — we cannot control this directly).
 *   2. Downsamples to 16000 Hz using linear interpolation.
 *   3. Converts float32 [-1, 1] samples to int16 [-32768, 32767].
 *   4. Posts the Int16Array to the main thread.
 *
 * The Gemini Live API expects: audio/pcm;rate=16000, 16-bit signed, mono.
 */

const TARGET_RATE = 16000;

class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // sampleRate is a global in AudioWorkletGlobalScope — the device's native rate
    this._ratio   = sampleRate / TARGET_RATE;
    this._phase   = 0;
    this._prevSample = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) return true;

    const out = [];

    for (let i = 0; i < channel.length; i++) {
      const current = channel[i];

      // Walk the output timeline at TARGET_RATE steps against the input timeline
      while (this._phase < 1) {
        // Linear interpolation between previous and current sample
        const sample = this._prevSample + this._phase * (current - this._prevSample);
        // Clamp and convert to int16
        const clamped = Math.max(-1, Math.min(1, sample));
        out.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF);
        this._phase += this._ratio;
      }

      this._phase    -= 1;
      this._prevSample = current;
    }

    if (out.length > 0) {
      const buf = new Int16Array(out);
      // Transfer ownership of the buffer (zero-copy) instead of copying it
      this.port.postMessage(buf, [buf.buffer]);
    }

    return true; // keep processor alive
  }
}

registerProcessor("pcm-processor", PCMProcessor);
