import { describe, expect, it, vi, beforeEach } from "vitest";
import { PersonaSocket } from "./PersonaSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly OPEN = 1;
  readyState = FakeWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
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

  it("reuses the in-flight connection instead of opening a second socket", async () => {
    class ConnectingFakeWebSocket extends FakeWebSocket {
      static readonly CONNECTING = 0;
      readyState = ConnectingFakeWebSocket.CONNECTING;
    }
    // @ts-expect-error test double
    globalThis.WebSocket = ConnectingFakeWebSocket;

    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const firstConnect = socket.connect();
    const secondConnect = socket.connect();

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(firstConnect).toBe(secondConnect);

    FakeWebSocket.instances[0].onopen?.();
    await firstConnect;
    await secondConnect;
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
        data: { persona_id: "abc", raw_summary: "", attributes: [], avatar_image: null, avatar_image_open: null },
      }),
    });

    expect(onResult).toHaveBeenCalledWith({
      persona_id: "abc",
      raw_summary: "",
      attributes: [],
      avatar_image: null,
      avatar_image_open: null,
    });
  });

  it("calls onAvatarError when an avatar_error message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onError = vi.fn();
    socket.onAvatarError = onError;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({ data: JSON.stringify({ type: "avatar_error", message: "no face detected" }) });

    expect(onError).toHaveBeenCalledWith("no face detected");
  });

  it("calls onFinishError when a finish_error message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onError = vi.fn();
    socket.onFinishError = onError;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({ data: JSON.stringify({ type: "finish_error", message: "gemini call failed" }) });

    expect(onError).toHaveBeenCalledWith("gemini call failed");
  });

  it("calls onStartError when a start_error message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onError = vi.fn();
    socket.onStartError = onError;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({ data: JSON.stringify({ type: "start_error", message: "model not found" }) });

    expect(onError).toHaveBeenCalledWith("model not found");
  });

  it("calls onAvatarTemplates when an avatar_templates message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onTemplates = vi.fn();
    socket.onAvatarTemplates = onTemplates;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    const templates = [{ id: "female_manga_mood", title: "Manga Mood", category: "Anime", gender: "female" }];
    ws.onmessage?.({ data: JSON.stringify({ type: "avatar_templates", data: templates }) });

    expect(onTemplates).toHaveBeenCalledWith(templates);
  });

  it("calls onDisconnected when the connection closes", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onDisconnected = vi.fn();
    socket.onDisconnected = onDisconnected;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onclose?.({ code: 1006, reason: "" });

    expect(onDisconnected).toHaveBeenCalledWith({ code: 1006, reason: "" });
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

  it("includes template_id in avatar_photo when given", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();
    const photo = new Uint8Array([9, 9, 9]).buffer;

    socket.sendAvatarPhoto(photo, "image/png", "female_manga_mood");

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sent.template_id).toBe("female_manga_mood");
  });

  it("omits template_id from avatar_photo when not given", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();
    const photo = new Uint8Array([9, 9, 9]).buffer;

    socket.sendAvatarPhoto(photo, "image/png");

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect("template_id" in sent).toBe(false);
  });

  it("appends the voice as a query param on the connecting URL", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect("Kore");

    expect(FakeWebSocket.instances[0].url).toBe("wss://example.test/ws/converse?voice=Kore");
  });

  it("connects without a query param when no voice is given", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();

    expect(FakeWebSocket.instances[0].url).toBe("wss://example.test/ws/converse");
  });

  it("calls onAvatarBaseImage when an avatar_base_image message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onAvatarBaseImage = vi.fn();
    socket.onAvatarBaseImage = onAvatarBaseImage;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({
      data: JSON.stringify({ type: "avatar_base_image", data: "base64imagedata", open_mouth_data: "openbase64" }),
    });

    expect(onAvatarBaseImage).toHaveBeenCalledWith("base64imagedata", "openbase64");
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
