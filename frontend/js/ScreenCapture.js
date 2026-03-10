/**
 * ScreenCapture.js — captures the user's screen via getDisplayMedia()
 * and emits JPEG frames at ~1 fps via a callback.
 *
 * React migration note: wrap this class in a useScreenCapture() hook.
 */

export class ScreenCapture {
  /**
   * @param {{ onFrame: (blob: Blob) => void, onStop?: () => void }} options
   */
  constructor({ onFrame, onStop }) {
    this._onFrame  = onFrame;
    this._onStop   = onStop ?? null;
    this._stream   = null;
    this._intervalId = null;

    // Offscreen canvas used to snapshot video frames
    this._canvas  = document.createElement("canvas");
    this._ctx     = this._canvas.getContext("2d");
    this._videoEl = document.getElementById("screenVideo");
  }

  /**
   * Requests screen share permission and starts the frame capture loop.
   * Throws if the user denies permission.
   */
  async start() {
    this._stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 1, max: 2 } },
      audio: false,
    });

    this._videoEl.srcObject = this._stream;
    await this._videoEl.play();

    // Capture one frame per second
    this._intervalId = setInterval(() => this._captureFrame(), 1000);

    // If the user stops sharing via the browser's built-in "Stop sharing" button
    this._stream.getVideoTracks()[0].addEventListener("ended", () => {
      this.stop();
      this._onStop?.();
    });
  }

  /** Stops the capture loop and releases the media stream. */
  stop() {
    clearInterval(this._intervalId);
    this._intervalId = null;

    if (this._stream) {
      this._stream.getTracks().forEach((t) => t.stop());
      this._stream = null;
    }

    this._videoEl.srcObject = null;
  }

  /** @private */
  _captureFrame() {
    const video = this._videoEl;
    if (video.readyState < video.HAVE_CURRENT_DATA) return;

    this._canvas.width  = video.videoWidth;
    this._canvas.height = video.videoHeight;
    this._ctx.drawImage(video, 0, 0);

    this._canvas.toBlob(
      (blob) => { if (blob) this._onFrame(blob); },
      "image/jpeg",
      0.8,  // quality — good compression vs. detail trade-off for code screenshots
    );
  }
}
