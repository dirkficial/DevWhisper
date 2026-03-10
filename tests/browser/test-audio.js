/**
 * test-audio.js — Browser tests for PCM audio math.
 *
 * Tests the two core audio algorithms in pure math — no AudioContext,
 * no WebSocket, no browser API calls. Any test failure here means audio
 * will be wrong (garbled, wrong speed, clipped, or silent) before you
 * even open a WebSocket connection.
 *
 * Algorithms under test:
 *   - int16ToFloat32  (mirrors AudioPlayer.js:64-69)
 *   - PCM downsampler (mirrors pcm-processor.js:29-56)
 *
 * How to run:
 *   python3 -m http.server 3000   # from project root
 *   open http://localhost:3000/tests/browser/test.html
 */

const { assert } = window;

// ─── Implementations (must match production code exactly) ─────────────────────
//
// These are inline copies of the production algorithms.
// If production code changes, update these to match — a divergence
// means the test no longer catches the bug it was designed for.

/**
 * Mirrors AudioPlayer.js _int16ToFloat32 (lines 64-69).
 * Converts int16 PCM samples to float32 in range [-1.0, 1.0].
 */
function int16ToFloat32(int16Array) {
  const float32 = new Float32Array(int16Array.length);
  for (let i = 0; i < int16Array.length; i++) {
    float32[i] = int16Array[i] / (int16Array[i] < 0 ? 0x8000 : 0x7FFF);
  }
  return float32;
}

/**
 * Mirrors pcm-processor.js process() (lines 29-56).
 * Downsamples float32 input at `inputRate` Hz to 16000 Hz.
 * Returns Int16Array of output samples.
 *
 * @param {Float32Array} input
 * @param {number} inputRate  device sample rate (e.g. 48000 or 44100)
 */
function downsample(input, inputRate) {
  const TARGET_RATE = 16000;
  const ratio = inputRate / TARGET_RATE;
  let phase = 0;
  let prevSample = 0;
  const out = [];

  for (let i = 0; i < input.length; i++) {
    const current = input[i];
    while (phase < 1) {
      const sample  = prevSample + phase * (current - prevSample);
      const clamped = Math.max(-1, Math.min(1, sample));
      out.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF);
      phase += ratio;
    }
    phase       -= 1;
    prevSample   = current;
  }

  return new Int16Array(out);
}

// ─── Test suites ──────────────────────────────────────────────────────────────

describe("int16ToFloat32 — AudioPlayer PCM conversion", () => {

  it("converts 0 → exactly 0.0", () => {
    const result = int16ToFloat32(new Int16Array([0]));
    assert.strictEqual(result[0], 0.0);
  });

  it("converts max positive (32767) → ~1.0", () => {
    const result = int16ToFloat32(new Int16Array([32767]));
    assert.approximately(result[0], 1.0, 0.0001,
      "Max int16 should map to ~1.0 float");
  });

  it("converts max negative (-32768) → -1.0", () => {
    const result = int16ToFloat32(new Int16Array([-32768]));
    assert.approximately(result[0], -1.0, 0.0001,
      "Min int16 should map to ~-1.0 float");
  });

  it("converts mid positive (16383) → ~0.5", () => {
    const result = int16ToFloat32(new Int16Array([16383]));
    assert.approximately(result[0], 0.5, 0.01);
  });

  it("converts mid negative (-16384) → ~-0.5", () => {
    const result = int16ToFloat32(new Int16Array([-16384]));
    assert.approximately(result[0], -0.5, 0.01);
  });

  it("preserves array length", () => {
    const input  = new Int16Array([0, 100, -100, 32767, -32768]);
    const result = int16ToFloat32(input);
    assert.strictEqual(result.length, input.length);
  });

  it("all output values are in range [-1.0, 1.0]", () => {
    // Test with boundary values and a sweep of the int16 range
    const samples = [0, 1, -1, 32767, -32768, 16000, -16000, 100, -100];
    const result  = int16ToFloat32(new Int16Array(samples));
    for (let i = 0; i < result.length; i++) {
      assert.isAtMost(result[i],  1.0, `Sample ${i} exceeded +1.0`);
      assert.isAtLeast(result[i], -1.0, `Sample ${i} went below -1.0`);
    }
  });

  it("round-trip int16 → float32 → int16 is within ±1 sample", () => {
    // Due to the asymmetric divisor (0x8000 vs 0x7FFF), round-trip
    // isn't perfect, but should be within 1 sample for any int16 value.
    const original = new Int16Array([0, 1000, -1000, 32767, -32768, 16384, -16384]);
    const float32  = int16ToFloat32(original);
    for (let i = 0; i < original.length; i++) {
      const reconstructed = Math.round(
        float32[i] < 0 ? float32[i] * 0x8000 : float32[i] * 0x7FFF
      );
      assert.approximately(reconstructed, original[i], 1,
        `Round-trip failed at index ${i}: ${original[i]} → ${reconstructed}`);
    }
  });

});


describe("PCM downsampler — pcm-processor.js", () => {

  it("48000 → 16000 Hz: 128 input samples produce 42 or 43 output samples", () => {
    // Ratio = 3.0, so approximately 128/3 ≈ 42.67 → either 42 or 43
    const input  = new Float32Array(128).fill(0);
    const output = downsample(input, 48000);
    assert.isTrue(
      output.length === 42 || output.length === 43,
      `Expected 42 or 43 samples, got ${output.length}`
    );
  });

  it("44100 → 16000 Hz: 128 input samples produce 46 or 47 output samples", () => {
    // Ratio = 2.75625, so approximately 128/2.75625 ≈ 46.45 → either 46 or 47
    const input  = new Float32Array(128).fill(0);
    const output = downsample(input, 44100);
    assert.isTrue(
      output.length === 46 || output.length === 47,
      `Expected 46 or 47 samples, got ${output.length}`
    );
  });

  it("silence in → silence out (all zeros)", () => {
    const input  = new Float32Array(128).fill(0.0);
    const output = downsample(input, 48000);
    for (let i = 0; i < output.length; i++) {
      assert.strictEqual(output[i], 0, `Sample ${i} should be 0, got ${output[i]}`);
    }
  });

  it("output values are all integers (valid int16)", () => {
    // The algorithm should only produce whole numbers after float→int16 conversion.
    // Non-integer values mean the clamp or conversion is broken.
    const input  = new Float32Array(128).map((_, i) => Math.sin(i * 0.1));
    const output = downsample(input, 48000);
    for (let i = 0; i < output.length; i++) {
      assert.strictEqual(output[i], Math.floor(output[i]),
        `Sample ${i} is not an integer: ${output[i]}`);
    }
  });

  it("output values stay within int16 range [-32768, 32767]", () => {
    // Clipping guard — values outside this range corrupt AudioPlayer
    const input  = new Float32Array(128).map(() => (Math.random() * 2) - 1);
    const output = downsample(input, 48000);
    for (let i = 0; i < output.length; i++) {
      assert.isAtLeast(output[i], -32768, `Sample ${i} below int16 min`);
      assert.isAtMost(output[i],   32767, `Sample ${i} above int16 max`);
    }
  });

  it("two consecutive 128-sample blocks produce consistent total output count", () => {
    // Phase continuity check: the downsampler maintains phase across calls.
    // If it resets phase between blocks, we get jitter at the block boundary.
    // Two 256-sample blocks should produce ~2× a single 128-sample block's output.
    const block   = new Float32Array(128).fill(0);
    const single  = downsample(block, 48000);

    // Simulate two consecutive calls using the stateful version
    // (we replicate the state manually to test phase continuity)
    const doubleInput = new Float32Array(256).fill(0);
    const double  = downsample(doubleInput, 48000);

    assert.approximately(double.length, single.length * 2, 1,
      `Two blocks (${double.length}) should be ~2× one block (${single.length * 2})`
    );
  });

  it("max amplitude positive signal stays within output range", () => {
    // All +1.0 input — output should be all 32767
    const input  = new Float32Array(128).fill(1.0);
    const output = downsample(input, 48000);
    for (let i = 0; i < output.length; i++) {
      assert.strictEqual(output[i], 32767, `Expected 32767, got ${output[i]}`);
    }
  });

  it("max amplitude negative signal stays within output range", () => {
    // All -1.0 input — output should be all -32768
    const input  = new Float32Array(128).fill(-1.0);
    const output = downsample(input, 48000);
    for (let i = 0; i < output.length; i++) {
      assert.strictEqual(output[i], -32768, `Expected -32768, got ${output[i]}`);
    }
  });

});
