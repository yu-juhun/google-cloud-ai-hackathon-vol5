export interface AudioPlayback {
  playChunk: (chunk: ArrayBuffer) => void;
  stop: () => void;
}

/** Plays back PCM16 audio chunks received from the Live API as they arrive,
 * queuing each chunk immediately after the previous one so playback stays
 * gapless. Gemini's native audio output is 24kHz mono PCM16. */
export function createAudioPlayback(sampleRate = 24000): AudioPlayback {
  const audioContext = new AudioContext();
  let nextStartTime = 0;

  return {
    playChunk(chunk: ArrayBuffer) {
      const pcm16 = new Int16Array(chunk);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 0x7fff;

      const buffer = audioContext.createBuffer(1, float32.length, sampleRate);
      buffer.copyToChannel(float32, 0);

      const source = audioContext.createBufferSource();
      source.buffer = buffer;
      source.connect(audioContext.destination);

      const startAt = Math.max(audioContext.currentTime, nextStartTime);
      source.start(startAt);
      nextStartTime = startAt + buffer.duration;
    },
    stop() {
      audioContext.close();
    },
  };
}
