import { describe, expect, it, vi, beforeEach } from "vitest";
import { PersonaSocket } from "./PersonaSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly OPEN = 1;
  readyState = FakeWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {}
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  // @ts-expect-error test double
  global.WebSocket = FakeWebSocket;
});

describe("PersonaSocket", () => {
  it("sends a base64 audio_chunk message", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();
    const chunk = new Uint8Array([1, 2, 3]).buffer;

    socket.sendAudioChunk(chunk);

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    assert_audio_chunk_message(sent);
  });

  it("sends a finish message", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();

    socket.sendFinish();

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sent).toEqual({ type: "finish" });
  });

  it("calls onPersonaResult when a persona_result message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onResult = vi.fn();
    socket.onPersonaResult = onResult;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({
      data: JSON.stringify({ type: "persona_result", data: { persona_id: "abc", raw_summary: "", attributes: [] } }),
    });

    expect(onResult).toHaveBeenCalledWith({ persona_id: "abc", raw_summary: "", attributes: [] });
  });
});

function assert_audio_chunk_message(sent: unknown) {
  expect(sent).toMatchObject({ type: "audio_chunk" });
  expect(typeof (sent as { data: string }).data).toBe("string");
}
