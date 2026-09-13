export interface MicCapture {
  stop: () => void;
}

const TARGET_SAMPLE_RATE = 16000;

/** Naive decimation to TARGET_SAMPLE_RATE. The `{ sampleRate: 16000 }`
 * AudioContext constructor option is not honored by every browser — many
 * silently keep the device's native rate (commonly 44100/48000Hz). Sending
 * un-resampled audio mislabeled as 16kHz plays back at the wrong pitch/speed
 * on the server side and produces garbage ASR transcripts, so this always
 * resamples explicitly based on the context's actual reported sampleRate
 * rather than assuming the constructor option took effect. */
function downsampleTo16k(input: Float32Array, inputSampleRate: number): Float32Array {
  if (inputSampleRate === TARGET_SAMPLE_RATE) return input;
  const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
  const outputLength = Math.round(input.length / ratio);
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i++) {
    output[i] = input[Math.floor(i * ratio)];
  }
  return output;
}

/** Captures mic audio, calling onChunk with raw PCM16 chunks (always
 * resampled to 16kHz regardless of the device's native rate) and onVolume
 * with a 0-1 volume estimate for each chunk (used to drive the avatar's
 * mouth toggle — see AvatarPanel). */
export function startMicCapture(
  onChunk: (chunk: ArrayBuffer) => void,
  onVolume: (level: number) => void,
): Promise<MicCapture> {
  return navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
    const audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    // Route through a silent gain node instead of audioContext.destination
    // directly — connecting the raw mic input to the destination plays it
    // straight back out the speakers, causing audible feedback/howling.
    const silentSink = audioContext.createGain();
    silentSink.gain.value = 0;

    processor.onaudioprocess = (event) => {
      const raw = event.inputBuffer.getChannelData(0);
      const input = downsampleTo16k(raw, audioContext.sampleRate);
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
    processor.connect(silentSink);
    silentSink.connect(audioContext.destination);

    return {
      stop: () => {
        processor.disconnect();
        source.disconnect();
        silentSink.disconnect();
        stream.getTracks().forEach((track) => track.stop());
        audioContext.close();
      },
    };
  });
}
