export interface MicCapture {
  stop: () => void;
}

const TARGET_SAMPLE_RATE = 16000;

/** AudioWorkletProcessor source, adapted from Google's official Live API
 * web console reference (google-gemini/live-api-web-console,
 * src/lib/worklets/audio-processing.ts, Apache-2.0). Runs on the dedicated
 * audio rendering thread rather than the main thread, so it keeps sampling
 * cleanly even while the main thread is busy (React re-renders, WebSocket
 * JSON/base64 encoding) — the deprecated ScriptProcessorNode this replaced
 * ran its callback on the main thread and was suspected of dropping/
 * corrupting samples under load, which lines up with the "unintelligible
 * transcript despite normal speech" symptom seen when testing this by
 * voice. Buffers 2048 int16 samples (~128ms at 16kHz) before flushing. */
const RECORDER_WORKLET_SOURCE = `
class PcmRecorderWorklet extends AudioWorkletProcessor {
  buffer = new Int16Array(2048);
  bufferWriteIndex = 0;

  process(inputs) {
    const channel0 = inputs[0] && inputs[0][0];
    if (channel0) {
      for (let i = 0; i < channel0.length; i++) {
        const sample = Math.max(-1, Math.min(1, channel0[i]));
        this.buffer[this.bufferWriteIndex++] = sample * 0x7fff;
        if (this.bufferWriteIndex >= this.buffer.length) {
          this.flush();
        }
      }
    }
    return true;
  }

  flush() {
    this.port.postMessage({ pcm16: this.buffer.slice(0, this.bufferWriteIndex).buffer });
    this.bufferWriteIndex = 0;
  }
}
`;

function createWorkletModuleUrl(workletName: string, processorSource: string): string {
  const script = new Blob([`registerProcessor("${workletName}", ${processorSource})`], {
    type: "application/javascript",
  });
  return URL.createObjectURL(script);
}

function rmsVolume(pcm16: ArrayBuffer): number {
  const view = new Int16Array(pcm16);
  let sumSquares = 0;
  for (let i = 0; i < view.length; i++) sumSquares += (view[i] / 0x7fff) ** 2;
  return view.length > 0 ? Math.sqrt(sumSquares / view.length) : 0;
}

/** Captures mic audio, calling onChunk with raw PCM16 chunks at 16kHz
 * (matching the Gemini Live API's required input format) and onVolume with
 * a 0-1 volume estimate for each chunk (used to drive the avatar's mouth
 * toggle — see AvatarPanel). */
export async function startMicCapture(
  onChunk: (chunk: ArrayBuffer) => void,
  onVolume: (level: number) => void,
): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
  const source = audioContext.createMediaStreamSource(stream);

  const workletName = "pcm-recorder-worklet";
  const moduleUrl = createWorkletModuleUrl(workletName, RECORDER_WORKLET_SOURCE);
  await audioContext.audioWorklet.addModule(moduleUrl);
  const recorderNode = new AudioWorkletNode(audioContext, workletName);

  recorderNode.port.onmessage = (event: MessageEvent<{ pcm16: ArrayBuffer }>) => {
    const chunk = event.data.pcm16;
    onChunk(chunk);
    onVolume(rmsVolume(chunk));
  };

  // AudioWorkletNode does not need to be connected to destination to keep
  // receiving input — unlike the deprecated ScriptProcessorNode, it is
  // driven directly by the render graph's active input connection.
  source.connect(recorderNode);

  return {
    stop: () => {
      recorderNode.port.onmessage = null;
      recorderNode.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      audioContext.close();
      URL.revokeObjectURL(moduleUrl);
    },
  };
}
