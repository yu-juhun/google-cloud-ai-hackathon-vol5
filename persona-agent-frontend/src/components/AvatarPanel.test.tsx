import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { AvatarPanel } from "./AvatarPanel";
import { PersonaSocket, AvatarTemplateCatalog } from "../ws/PersonaSocket";
import * as micCapture from "../audio/micCapture";

vi.mock("../ws/PersonaSocket");

const SAMPLE_CATALOG: AvatarTemplateCatalog = {
  female: { Anime: [{ id: "female_manga_mood", title: "Manga Mood", thumb: null }] },
  male: { Lifestyle: [{ id: "male_yearbook", title: "Yearbook", thumb: null }] },
};

/** Renders with a template catalog already resolved (mirrors the mount-time
 * fetchAvatarTemplates() call), then selects a gender + style tile so the
 * photo upload is enabled — the realistic path a user takes now that both
 * are required. */
async function renderReadyToUpload(catalog: AvatarTemplateCatalog = SAMPLE_CATALOG, socket?: PersonaSocket) {
  const s = socket ?? new PersonaSocket("wss://example.test");
  s.fetchAvatarTemplates = vi.fn().mockResolvedValue(catalog);
  render(<AvatarPanel socket={s} />);
  await act(async () => {});

  const [gender, categories] = Object.entries(catalog)[0];
  const [, entries] = Object.entries(categories)[0];
  fireEvent.click(screen.getByRole("radio", { name: gender === "female" ? "女性" : "男性" }));
  fireEvent.click(screen.getByRole("radio", { name: new RegExp(entries[0].title) }));

  return s;
}

describe("AvatarPanel", () => {
  it("shows the closed-mouth avatar by default", () => {
    render(<AvatarPanel socket={new PersonaSocket("wss://example.test")} />);
    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toContain("avatar-default-closed.png");
  });

  it("shows a finish button that calls socket.sendFinish", () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.sendFinish = vi.fn();
    render(<AvatarPanel socket={socket} />);

    fireEvent.click(screen.getByRole("button", { name: "完了" }));

    expect(socket.sendFinish).toHaveBeenCalled();
  });

  it("stops the mic capture on unmount, not just on 完了", async () => {
    const stop = vi.fn();
    const startMicCaptureSpy = vi
      .spyOn(micCapture, "startMicCapture")
      .mockResolvedValue({ stop });
    const socket = new PersonaSocket("wss://example.test");
    socket.connect = vi.fn().mockResolvedValue(undefined);
    const { unmount } = render(<AvatarPanel socket={socket} />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "話しかける" }));
    });

    unmount();

    expect(stop).toHaveBeenCalled();
    startMicCaptureSpy.mockRestore();
  });

  it("only shows styles for the selected gender, and requires a gender first", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.fetchAvatarTemplates = vi.fn().mockResolvedValue(SAMPLE_CATALOG);
    render(<AvatarPanel socket={socket} />);
    await act(async () => {});

    expect(screen.queryByRole("radio", { name: /Manga Mood/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Yearbook/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "女性" }));

    expect(screen.getByRole("radio", { name: /Manga Mood/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Yearbook/ })).not.toBeInTheDocument();
  });

  it("disables the photo upload until both gender and style are chosen", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.fetchAvatarTemplates = vi.fn().mockResolvedValue(SAMPLE_CATALOG);
    render(<AvatarPanel socket={socket} />);
    await act(async () => {});

    expect(screen.getByLabelText("先に性別とスタイルを選んでください")).toBeDisabled();

    fireEvent.click(screen.getByRole("radio", { name: "女性" }));
    expect(screen.getByLabelText("先に性別とスタイルを選んでください")).toBeDisabled();

    fireEvent.click(screen.getByRole("radio", { name: /Manga Mood/ }));
    expect(screen.getByLabelText("顔写真をアップロード")).not.toBeDisabled();
  });

  it("shows an error message when the connection drops before finishing", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onDisconnected?.({} as CloseEvent);
    });

    expect(screen.getByRole("alert")).toHaveTextContent("接続が予期せず切断されました");
  });

  it("does not show a disconnect error if the persona result already arrived", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onPersonaResult?.({
        persona_id: "abc",
        raw_summary: "テスト要約",
        attributes: [],
        schema_version: "2",
        avatar_image: null,
        avatar_image_open: null,
      });
    });
    act(() => {
      socket.onDisconnected?.({} as CloseEvent);
    });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error message if starting the conversation fails", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.connect = vi.fn().mockRejectedValue(new Error("mic permission denied"));
    render(<AvatarPanel socket={socket} />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "話しかける" }));
    });

    expect(screen.getByRole("alert")).toHaveTextContent("mic permission denied");
  });

  it("shows an error message if sending the photo fails", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.connect = vi.fn().mockRejectedValue(new Error("connection refused"));
    await renderReadyToUpload(SAMPLE_CATALOG, socket);

    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText("顔写真をアップロード") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(screen.getByRole("alert")).toHaveTextContent("connection refused");
  });

  it("displays the persona result once onPersonaResult fires", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onPersonaResult?.({
        persona_id: "abc",
        raw_summary: "テスト要約",
        attributes: [],
        schema_version: "2",
        avatar_image: null,
        avatar_image_open: null,
      });
    });

    expect(screen.getByText("テスト要約")).toBeInTheDocument();
  });

  it("shows a photo upload input before the conversation starts, initially disabled", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.fetchAvatarTemplates = vi.fn().mockResolvedValue(SAMPLE_CATALOG);
    render(<AvatarPanel socket={socket} />);
    await act(async () => {});

    expect(screen.getByLabelText("先に性別とスタイルを選んでください")).toBeDisabled();
  });

  it("sends the selected photo and its template_id via socket.sendAvatarPhoto", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.sendAvatarPhoto = vi.fn();
    await renderReadyToUpload(SAMPLE_CATALOG, socket);

    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText("顔写真をアップロード") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(socket.sendAvatarPhoto).toHaveBeenCalledWith(expect.anything(), "image/png", "female_manga_mood");
  });

  it("connects with the selected voice when starting the conversation", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.connect = vi.fn().mockResolvedValue(undefined);
    render(<AvatarPanel socket={socket} />);

    fireEvent.change(screen.getByLabelText("声を選ぶ"), { target: { value: "Kore" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "話しかける" }));
    });

    expect(socket.connect).toHaveBeenCalledWith("Kore");
  });

  it("shows the avatar_error message", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarError?.("no face detected");
    });

    expect(screen.getByRole("alert")).toHaveTextContent("no face detected");
  });

  it("clears a previous avatar_error once a later avatar_base_image succeeds", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarError?.("no face detected");
    });
    act(() => {
      socket.onAvatarBaseImage?.("base64data", "open-base64data");
    });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("displays the avatar_base_image once received", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarBaseImage?.("base64data", "open-base64data");
    });

    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toBe("data:image/png;base64,base64data");
  });

  it("switches to the evolved persona.avatar_image once persona_result arrives", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarBaseImage?.("base64data", "open-base64data");
    });
    act(() => {
      socket.onPersonaResult?.({
        persona_id: "abc",
        raw_summary: "テスト要約",
        attributes: [],
        schema_version: "2",
        avatar_image: "evolved-base64data",
        avatar_image_open: "evolved-open-base64data",
      });
    });

    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toBe("data:image/png;base64,evolved-base64data");
  });

  it("shows the personalized open-mouth image while the model is speaking", () => {
    // createAudioPlayback() needs a real AudioContext, which jsdom doesn't
    // provide — stub just enough of it for onAudioChunk's playback call.
    class FakeAudioContext {
      currentTime = 0;
      createBuffer() {
        return { copyToChannel: vi.fn(), duration: 0 };
      }
      createBufferSource() {
        return { connect: vi.fn(), start: vi.fn() };
      }
      close() {}
    }
    // @ts-expect-error test stub
    globalThis.AudioContext = FakeAudioContext;

    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarBaseImage?.("base64data", "open-base64data");
    });
    act(() => {
      // Simulate the model speaking: onAudioChunk sets mouthOpen based on
      // volume. Directly drive it via a loud PCM16 chunk instead of
      // reaching into component internals.
      const loudSample = 0x7fff;
      const samples = new Int16Array(100).fill(loudSample);
      socket.onAudioChunk?.(samples.buffer);
    });

    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toBe("data:image/png;base64,open-base64data");
  });

  it("connects the socket when a photo is selected before starting the conversation", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.connect = vi.fn().mockResolvedValue(undefined);
    socket.sendAvatarPhoto = vi.fn();
    await renderReadyToUpload(SAMPLE_CATALOG, socket);

    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText("顔写真をアップロード") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(socket.connect).toHaveBeenCalled();
    expect(socket.sendAvatarPhoto).toHaveBeenCalled();
  });
});
