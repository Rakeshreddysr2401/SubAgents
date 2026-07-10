import { useState } from "react";
import type { InterruptItemProps } from "./types";

/** ask_user_choice: the agent's structured question rendered as tappable
 * options + a free-text "something else". The selection returns to the model
 * as the tool result (decision type "respond"). */
export function ChoiceCard({ request, decided, disabled, onDecide }: InterruptItemProps) {
  const [custom, setCustom] = useState("");
  const question = String(request.args.question ?? "Please choose:");
  const options = Array.isArray(request.args.options)
    ? (request.args.options as unknown[]).map(String)
    : [];

  if (decided) {
    return (
      <div className="interrupt-item">
        <div className="choice-question">{question}</div>
        <div className="interrupt-decided">
          {decided.type === "respond" ? <>You chose: <strong>{decided.message}</strong></> : "Dismissed"}
        </div>
      </div>
    );
  }

  const sendCustom = () => {
    const text = custom.trim();
    if (text) onDecide({ type: "respond", message: text });
  };

  return (
    <div className="interrupt-item">
      <div className="choice-question">{question}</div>
      <div className="choice-options">
        {options.map((option) => (
          <button
            key={option}
            className="choice-option"
            onClick={() => onDecide({ type: "respond", message: option })}
            disabled={disabled}
            type="button"
          >
            {option}
          </button>
        ))}
      </div>
      <div className="choice-custom">
        <input
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") sendCustom(); }}
          placeholder="Something else…"
          disabled={disabled}
        />
        <button onClick={sendCustom} disabled={disabled || !custom.trim()} type="button" aria-label="Send answer">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      </div>
      <button
        className="choice-dismiss"
        onClick={() => onDecide({ type: "reject" })}
        disabled={disabled}
        type="button"
      >
        Dismiss
      </button>
    </div>
  );
}
