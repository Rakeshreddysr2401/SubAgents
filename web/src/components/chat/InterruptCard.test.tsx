/** HITL decision collection: one decision per action request, resolved only
 * when every request is decided; edits must produce valid edited_action. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ActionRequest } from "../../api/types";
import { InterruptCard } from "./InterruptCard";

const openApp: ActionRequest = { name: "open_mac_app", args: { app_name: "Safari" } };
const confirmOrder: ActionRequest = { name: "confirm_order", args: { cart_id: "c1" } };

describe("InterruptCard", () => {
  it("approve resolves a single request immediately", () => {
    const onResolve = vi.fn();
    render(<InterruptCard actionRequests={[openApp]} onResolve={onResolve} resolving={false} />);
    fireEvent.click(screen.getByText("Approve"));
    expect(onResolve).toHaveBeenCalledWith([{ type: "approve" }]);
  });

  it("reject resolves with a reject decision", () => {
    const onResolve = vi.fn();
    render(<InterruptCard actionRequests={[openApp]} onResolve={onResolve} resolving={false} />);
    fireEvent.click(screen.getByText("Reject"));
    expect(onResolve).toHaveBeenCalledWith([{ type: "reject" }]);
  });

  it("waits until EVERY action request is decided", () => {
    const onResolve = vi.fn();
    render(
      <InterruptCard actionRequests={[openApp, confirmOrder]} onResolve={onResolve} resolving={false} />,
    );
    fireEvent.click(screen.getAllByText("Approve")[0]);
    expect(onResolve).not.toHaveBeenCalled(); // second still pending
    fireEvent.click(screen.getAllByText("Reject")[0]);
    expect(onResolve).toHaveBeenCalledWith([{ type: "approve" }, { type: "reject" }]);
  });

  it("edit produces an edited_action with the parsed args", () => {
    const onResolve = vi.fn();
    render(<InterruptCard actionRequests={[openApp]} onResolve={onResolve} resolving={false} />);
    fireEvent.click(screen.getByText("Edit"));
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: '{"app_name": "Notes"}' } });
    fireEvent.click(screen.getByText(/Save & approve/));
    expect(onResolve).toHaveBeenCalledWith([
      { type: "edit", edited_action: { name: "open_mac_app", args: { app_name: "Notes" } } },
    ]);
  });

  it("invalid JSON keeps the editor open and does not resolve", () => {
    const onResolve = vi.fn();
    render(<InterruptCard actionRequests={[openApp]} onResolve={onResolve} resolving={false} />);
    fireEvent.click(screen.getByText("Edit"));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "{broken" } });
    fireEvent.click(screen.getByText(/Save & approve/));
    expect(onResolve).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("buttons disabled while resolving", () => {
    render(<InterruptCard actionRequests={[openApp]} onResolve={vi.fn()} resolving={true} />);
    expect(screen.getByText("Approve")).toBeDisabled();
    expect(screen.getByText("Reject")).toBeDisabled();
  });
});
