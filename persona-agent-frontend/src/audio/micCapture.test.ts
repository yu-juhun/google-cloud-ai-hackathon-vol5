import { describe, expect, it } from "vitest";
import { rmsVolume } from "./micCapture";

describe("rmsVolume", () => {
  it("returns 0 for silence", () => {
    const samples = new Int16Array(100).fill(0);
    expect(rmsVolume(samples.buffer)).toBe(0);
  });

  it("returns 1 for a full-scale constant tone", () => {
    const samples = new Int16Array(100).fill(0x7fff);
    expect(rmsVolume(samples.buffer)).toBeCloseTo(1, 3);
  });

  it("returns 0 for an empty buffer instead of NaN", () => {
    const samples = new Int16Array(0);
    expect(rmsVolume(samples.buffer)).toBe(0);
  });

  it("scales with amplitude", () => {
    const quiet = new Int16Array(100).fill(0x1000);
    const loud = new Int16Array(100).fill(0x4000);
    expect(rmsVolume(loud.buffer)).toBeGreaterThan(rmsVolume(quiet.buffer));
  });
});
