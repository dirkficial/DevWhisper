/**
 * AudioPlayer.js — plays back 24 kHz PCM audio chunks received from the agent.
 *
 * Uses back-to-back AudioBuffer scheduling to play chunks seamlessly without
 * gaps or clicks between them.
 *
 * React migration note: wrap this class in a useAudioPlayer() hook.
 */

const AGENT_SAMPLE_RATE = 24000; // Gemini Live API output rate

export class AudioPlayer {
  constructor() {
    this._ctx          = null;
    this._nextPlayTime = 0; // when to schedule the next buffer
  }

  /** Lazily creates the AudioContext on first play (avoids autoplay policy issues). */
  _ensureContext() {
    if (!this._ctx) {
      this._ctx = new AudioContext({ sampleRate: AGENT_SAMPLE_RATE });
      this._nextPlayTime = this._ctx.currentTime;
    }

    // Resume if suspended (browser autoplay policy)
    if (this._ctx.state === "suspended") {
      this._ctx.resume();
    }
  }

  /**
   * Schedules an Int16Array PCM chunk for seamless playback.
   * @param {Int16Array} int16Array
   */
  play(int16Array) {
    this._ensureContext();

    const float32 = this._int16ToFloat32(int16Array);

    const buffer = this._ctx.createBuffer(1, float32.length, AGENT_SAMPLE_RATE);
    buffer.copyToChannel(float32, 0);

    const source = this._ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this._ctx.destination);

    // Schedule immediately if we've fallen behind (e.g. after a gap)
    const startAt = Math.max(this._ctx.currentTime, this._nextPlayTime);
    source.start(startAt);

    this._nextPlayTime = startAt + buffer.duration;
  }

  /** Immediately cancels all scheduled audio buffers (e.g. on agent interruption). */
  interrupt() {
    if (this._ctx) {
      this._ctx.close();  // immediately halts all scheduled AudioBufferSourceNodes
      this._ctx = null;
      this._nextPlayTime = 0;
    }
  }

  /** Stops playback and closes the AudioContext. */
  stop() {
    if (this._ctx) {
      this._ctx.close();
      this._ctx = null;
      this._nextPlayTime = 0;
    }
  }

  /** @private — converts int16 [-32768, 32767] to float32 [-1.0, 1.0] */
  _int16ToFloat32(int16Array) {
    const float32 = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32[i] = int16Array[i] / (int16Array[i] < 0 ? 0x8000 : 0x7FFF);
    }
    return float32;
  }
}
