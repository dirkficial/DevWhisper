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

    // Native-resolution canvas for frame differencing hash sampling
    this._canvas  = document.createElement("canvas");
    this._ctx     = this._canvas.getContext("2d");
    // Resized canvas for encoding (max 1280px wide)
    this._encCanvas = document.createElement("canvas");
    this._encCtx    = this._encCanvas.getContext("2d");
    this._lastSamples = null;
    this._videoEl = document.getElementById("screenVideo");
  }

  /**
   * Requests screen share permission and starts the frame capture loop.
   * Throws if the user denies permission.
   */
  async start() {
    this._stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 0.5, max: 1 } },
      audio: false,
    });

    this._videoEl.srcObject = this._stream;
    await this._videoEl.play();

    // Capture one frame every 2 seconds (0.5 fps) to reduce Gemini context load
    this._intervalId = setInterval(() => this._captureFrame(), 2000);

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

    // Draw at native resolution for hash sampling
    const W = video.videoWidth, H = video.videoHeight;
    this._canvas.width  = W;
    this._canvas.height = H;
    this._ctx.drawImage(video, 0, 0);

    // Frame differencing: sample 100 pixels in a 10×10 grid
    // Use top 80% of height to avoid any on-screen overlay/log UI in the shared view
    const stepX = Math.floor(W / 10), stepY = Math.floor((H * 0.8) / 10);
    const newSamples = [];
    for (let r = 0; r < 10; r++) {
      for (let c = 0; c < 10; c++) {
        const px = this._ctx.getImageData(c * stepX, r * stepY, 1, 1).data;
        newSamples.push(px[0], px[1], px[2]);
      }
    }
    if (this._lastSamples) {
      let changed = 0;
      for (let i = 0; i < newSamples.length; i += 3) {
        const dr = Math.abs(newSamples[i]   - this._lastSamples[i]);
        const dg = Math.abs(newSamples[i+1] - this._lastSamples[i+1]);
        const db = Math.abs(newSamples[i+2] - this._lastSamples[i+2]);
        if (dr + dg + db > 30) changed++;
      }
      if (changed < 8) return;  // <8% of samples changed — skip this frame
    }
    this._lastSamples = newSamples;

    // Resize to max 1280px wide for encoding (reduces Gemini tile count by ~3×)
    const MAX_W = 1280;
    const encW = W > MAX_W ? MAX_W : W;
    const encH = W > MAX_W ? Math.round(H * MAX_W / W) : H;
    this._encCanvas.width  = encW;
    this._encCanvas.height = encH;
    this._encCtx.drawImage(this._canvas, 0, 0, encW, encH);

    this._encCanvas.toBlob(
      (blob) => { if (blob) this._onFrame(blob); },
      "image/jpeg",
      0.75,
    );
  }
}
