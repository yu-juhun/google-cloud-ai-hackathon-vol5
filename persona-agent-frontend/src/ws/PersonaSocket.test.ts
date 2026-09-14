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
      data: JSON.stringify({
        type: "persona_result",
        data: { persona_id: "abc", raw_summary: "", attributes: [], avatar_image: null },
      }),
    });

    expect(onResult).toHaveBeenCalledWith({ persona_id: "abc", raw_summary: "", attributes: [], avatar_image: null });
  });

  it("sends a base64 avatar_photo message with content_type", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();
    const photo = new Uint8Array([9, 9, 9]).buffer;

    socket.sendAvatarPhoto(photo, "image/png");

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sent.type).toBe("avatar_photo");
    expect(sent.content_type).toBe("image/png");
    expect(typeof sent.data).toBe("string");
  });

  it("calls onAvatarBaseImage when an avatar_base_image message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onAvatarBaseImage = vi.fn();
    socket.onAvatarBaseImage = onAvatarBaseImage;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({ data: JSON.stringify({ type: "avatar_base_image", data: "base64imagedata" }) });

    expect(onAvatarBaseImage).toHaveBeenCalledWith("base64imagedata");
  });

  it("does not open a second WebSocket when already connected", async () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const firstConnect = socket.connect();
    FakeWebSocket.instances[0].onopen?.();
    await firstConnect;

    await socket.connect();

    expect(FakeWebSocket.instances.length).toBe(1);
  });
});

function assert_audio_chunk_message(sent: unknown) {
  expect(sent).toMatchObject({ type: "audio_chunk" });
  expect(typeof (sent as { data: string }).data).toBe("string");
}
