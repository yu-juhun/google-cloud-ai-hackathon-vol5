import { describe, expect, it, vi } from "vitest";
import { createAudioPlayback } from "./audioPlayback";

class FakeAudioBufferSource {
  buffer: unknown = null;
  connect = vi.fn();
  start = vi.fn();
}

class FakeAudioContext {
  currentTime = 0;
  createdBuffers: { channelData: Float32Array; sampleRate: number }[] = [];
  sources: FakeAudioBufferSource[] = [];
  destination = {};

  createBuffer(_channels: number, length: number, sampleRate: number) {
    const channelData = new Float32Array(length);
    this.createdBuffers.push({ channelData, sampleRate });
    return {
      duration: length / sampleRate,
      copyToChannel: (data: Float32Array) => channelData.set(data),
    };
  }

  createBufferSource() {
    const source = new FakeAudioBufferSource();
    this.sources.push(source);
    return source;
  }

  close = vi.fn();
}

describe("createAudioPlayback", () => {
  it("schedules chunks back-to-back without gaps", () => {
    let created: FakeAudioContext | null = null;
    class TrackedFakeAudioContext extends FakeAudioContext {
      constructor() {
        super();
        created = this;
      }
    }
    // @ts-expect-error test stub
    globalThis.AudioContext = TrackedFakeAudioContext;

    const playback = createAudioPlayback(24000);
    const ctx = created!;

    const chunk = new Int16Array(24000).fill(0x1000); // 1 second at 24kHz
    playback.playChunk(chunk.buffer);
    playback.playChunk(chunk.buffer);

    expect(ctx.sources).toHaveLength(2);
    expect(ctx.sources[0].start).toHaveBeenCalledWith(0);
    expect(ctx.sources[1].start).toHaveBeenCalledWith(1); // starts right after the first chunk's 1s duration
  });

  it("normalizes int16 samples into the -1..1 float32 range", () => {
    let created: FakeAudioContext | null = null;
    class TrackedFakeAudioContext extends FakeAudioContext {
      constructor() {
        super();
        created = this;
      }
    }
    // @ts-expect-error test stub
    globalThis.AudioContext = TrackedFakeAudioContext;

    const playback = createAudioPlayback(24000);
    const ctx = created!;

    playback.playChunk(new Int16Array([0x7fff, -0x7fff, 0]).buffer);

    const [{ channelData }] = ctx.createdBuffers;
    expect(channelData[0]).toBeCloseTo(1, 3);
    expect(channelData[1]).toBeCloseTo(-1, 3);
    expect(channelData[2]).toBe(0);
  });

  it("closes the underlying AudioContext on stop", () => {
    let created: FakeAudioContext | null = null;
    class TrackedFakeAudioContext extends FakeAudioContext {
      constructor() {
        super();
        created = this;
      }
    }
    // @ts-expect-error test stub
    globalThis.AudioContext = TrackedFakeAudioContext;

    const playback = createAudioPlayback(24000);
    playback.stop();

    expect(created!.close).toHaveBeenCalled();
  });
});
