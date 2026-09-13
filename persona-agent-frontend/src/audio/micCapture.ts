export interface MicCapture {
  stop: () => void;
}

/** Captures mic audio, calling onChunk with raw PCM16 chunks and onVolume
 * with a 0-1 volume estimate for each chunk (used to drive the avatar's
 * mouth toggle — see AvatarPanel). */
export function startMicCapture(
  onChunk: (chunk: ArrayBuffer) => void,
  onVolume: (level: number) => void,
): Promise<MicCapture> {
  return navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
    const audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      const pcm16 = new Int16Array(input.length);
      let sumSquares = 0;
      for (let i = 0; i < input.length; i++) {
        const sample = Math.max(-1, Math.min(1, input[i]));
        pcm16[i] = sample * 0x7fff;
        sumSquares += sample * sample;
      }
      onChunk(pcm16.buffer);
      onVolume(Math.sqrt(sumSquares / input.length));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    return {
      stop: () => {
        processor.disconnect();
        source.disconnect();
        stream.getTracks().forEach((track) => track.stop());
        audioContext.close();
      },
    };
  });
}
