import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { AvatarPanel } from "./AvatarPanel";
import { PersonaSocket } from "../ws/PersonaSocket";

vi.mock("../ws/PersonaSocket");

describe("AvatarPanel", () => {
  it("shows the closed-mouth avatar by default", () => {
    render(<AvatarPanel socket={new PersonaSocket("wss://example.test")} />);
    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toContain("avatar-mouth-closed.svg");
  });

  it("shows a finish button that calls socket.sendFinish", () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.sendFinish = vi.fn();
    render(<AvatarPanel socket={socket} />);

    fireEvent.click(screen.getByRole("button", { name: "完了" }));

    expect(socket.sendFinish).toHaveBeenCalled();
  });

  it("displays the persona result once onPersonaResult fires", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onPersonaResult?.({
        persona_id: "abc",
        raw_summary: "テスト要約",
        attributes: [],
        avatar_image: null,
      });
    });

    expect(screen.getByText("テスト要約")).toBeInTheDocument();
  });

  it("shows a photo upload input before the conversation starts", () => {
    render(<AvatarPanel socket={new PersonaSocket("wss://example.test")} />);
    expect(screen.getByLabelText("顔写真をアップロード")).toBeInTheDocument();
  });

  it("sends the selected photo via socket.sendAvatarPhoto", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.sendAvatarPhoto = vi.fn();
    render(<AvatarPanel socket={socket} />);

    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText("顔写真をアップロード") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(socket.sendAvatarPhoto).toHaveBeenCalled();
    const [, contentType] = (socket.sendAvatarPhoto as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(contentType).toBe("image/png");
  });

  it("displays the avatar_base_image once received", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarBaseImage?.("base64data");
    });

    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toBe("data:image/png;base64,base64data");
  });

  it("switches to the evolved persona.avatar_image once persona_result arrives", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarBaseImage?.("base64data");
    });
    act(() => {
      socket.onPersonaResult?.({
        persona_id: "abc",
        raw_summary: "テスト要約",
        attributes: [],
        avatar_image: "evolved-base64data",
      });
    });

    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toBe("data:image/png;base64,evolved-base64data");
  });

  it("connects the socket when a photo is selected before starting the conversation", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.connect = vi.fn().mockResolvedValue(undefined);
    socket.sendAvatarPhoto = vi.fn();
    render(<AvatarPanel socket={socket} />);

    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText("顔写真をアップロード") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(socket.connect).toHaveBeenCalled();
    expect(socket.sendAvatarPhoto).toHaveBeenCalled();
  });
});
