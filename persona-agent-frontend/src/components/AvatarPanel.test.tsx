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
      });
    });

    expect(screen.getByText("テスト要約")).toBeInTheDocument();
  });
});
