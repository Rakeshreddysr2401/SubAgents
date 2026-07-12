import { useState, type ComponentType } from "react";
import type { ActionRequest, ResumeDecision } from "../../api/types";
import { ChoiceCard } from "./interrupts/ChoiceCard";
import { OrderConfirmCard } from "./interrupts/OrderConfirmCard";
import type { InterruptItemProps } from "./interrupts/types";
import "./ActivityCards.css";

/** Component registry: the interrupt's action name is the component id.
 * Anything unregistered renders through the generic JSON card, so new gated
 * tools work day one and can be upgraded to rich cards later. */
const RICH_COMPONENTS: Record<string, ComponentType<InterruptItemProps>> = {
  ask_user_choice: ChoiceCard,
  // The real spend/commit steps on Swiggy's live MCP servers, plus the
  // generic confirm — all get the amount-forward order card.
  confirm_order: OrderConfirmCard,
  place_food_order: OrderConfirmCard,
  checkout: OrderConfirmCard,
};

interface InterruptCardProps {
  actionRequests: ActionRequest[];
  onResolve: (decisions: ResumeDecision[]) => void;
  resolving: boolean;
}

function friendlyToolName(name: string): string {
  return name.replace(/_/g, " ");
}

/** The unregistered-tool fallback: raw args + approve/edit/reject. */
function GenericActionItem({ request, decided, disabled, onDecide }: InterruptItemProps) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");

  const startEdit = () => {
    setEditing(true);
    setEditText(JSON.stringify(request.args, null, 2));
  };

  const confirmEdit = () => {
    try {
      const args = JSON.parse(editText);
      onDecide({ type: "edit", edited_action: { name: request.name, args } });
      setEditing(false);
    } catch {
      // leave the textarea open on invalid JSON
    }
  };

  return (
    <div className="interrupt-item">
      <div className="interrupt-item-title">{friendlyToolName(request.name)}</div>
      {editing ? (
        <>
          <textarea
            className="interrupt-edit-textarea"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            rows={4}
          />
          <div className="interrupt-actions">
            <button className="interrupt-btn approve" onClick={confirmEdit} type="button">
              Save &amp; approve
            </button>
            <button className="interrupt-btn" onClick={() => setEditing(false)} type="button">
              Cancel
            </button>
          </div>
        </>
      ) : (
        <>
          <pre className="interrupt-args">{JSON.stringify(request.args, null, 2)}</pre>
          {decided ? (
            <div className="interrupt-decided">
              Resolved: <strong>{decided.type}</strong>
            </div>
          ) : (
            <div className="interrupt-actions">
              <button
                className="interrupt-btn approve"
                onClick={() => onDecide({ type: "approve" })}
                disabled={disabled}
                type="button"
              >
                Approve
              </button>
              <button className="interrupt-btn" onClick={startEdit} disabled={disabled} type="button">
                Edit
              </button>
              <button
                className="interrupt-btn reject"
                onClick={() => onDecide({ type: "reject" })}
                disabled={disabled}
                type="button"
              >
                Reject
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function InterruptCard({ actionRequests, onResolve, resolving }: InterruptCardProps) {
  const [decisions, setDecisions] = useState<(ResumeDecision | null)[]>(
    () => actionRequests.map(() => null),
  );

  const setDecisionAt = (index: number, decision: ResumeDecision) => {
    const next = [...decisions];
    next[index] = decision;
    setDecisions(next);
    if (next.every((d) => d !== null)) {
      onResolve(next as ResumeDecision[]);
    }
  };

  // A card full of questions is an input request, not an approval request —
  // the header should say so.
  const questionsOnly = actionRequests.every((ar) => ar.name === "ask_user_choice");

  return (
    <div className={`interrupt-card${questionsOnly ? " question-mode" : ""}`}>
      <div className="interrupt-card-header">
        {questionsOnly ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        )}
        {questionsOnly ? "Your input needed" : "Approval needed"}
      </div>
      {actionRequests.map((ar, i) => {
        const Item = RICH_COMPONENTS[ar.name] ?? GenericActionItem;
        return (
          <Item
            key={i}
            request={ar}
            decided={decisions[i]}
            disabled={resolving}
            onDecide={(d) => setDecisionAt(i, d)}
          />
        );
      })}
    </div>
  );
}
