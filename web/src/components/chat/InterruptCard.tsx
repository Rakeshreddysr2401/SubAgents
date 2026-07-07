import { useState } from "react";
import type { ActionRequest, ResumeDecision } from "../../api/types";

interface InterruptCardProps {
  actionRequests: ActionRequest[];
  onResolve: (decisions: ResumeDecision[]) => void;
  resolving: boolean;
}

function friendlyToolName(name: string): string {
  return name.replace(/_/g, " ");
}

export function InterruptCard({ actionRequests, onResolve, resolving }: InterruptCardProps) {
  const [decisions, setDecisions] = useState<(ResumeDecision | null)[]>(
    () => actionRequests.map(() => null),
  );
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editText, setEditText] = useState("");

  const setDecisionAt = (index: number, decision: ResumeDecision) => {
    const next = [...decisions];
    next[index] = decision;
    setDecisions(next);
    if (next.every((d) => d !== null)) {
      onResolve(next as ResumeDecision[]);
    }
  };

  const startEdit = (index: number) => {
    setEditingIndex(index);
    setEditText(JSON.stringify(actionRequests[index].args, null, 2));
  };

  const confirmEdit = (index: number) => {
    try {
      const args = JSON.parse(editText);
      setDecisionAt(index, { type: "edit", edited_action: { name: actionRequests[index].name, args } });
      setEditingIndex(null);
    } catch {
      // leave the textarea open on invalid JSON
    }
  };

  return (
    <div className="interrupt-card">
      <div className="interrupt-card-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        Approval needed
      </div>
      {actionRequests.map((ar, i) => {
        const decided = decisions[i];
        return (
          <div key={i} className="interrupt-item">
            <div className="interrupt-item-title">{friendlyToolName(ar.name)}</div>
            {editingIndex === i ? (
              <>
                <textarea
                  className="interrupt-edit-textarea"
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  rows={4}
                />
                <div className="interrupt-actions">
                  <button className="interrupt-btn approve" onClick={() => confirmEdit(i)} type="button">
                    Save &amp; approve
                  </button>
                  <button className="interrupt-btn" onClick={() => setEditingIndex(null)} type="button">
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <pre className="interrupt-args">{JSON.stringify(ar.args, null, 2)}</pre>
                {decided ? (
                  <div className="interrupt-decided">
                    Resolved: <strong>{decided.type}</strong>
                  </div>
                ) : (
                  <div className="interrupt-actions">
                    <button
                      className="interrupt-btn approve"
                      onClick={() => setDecisionAt(i, { type: "approve" })}
                      disabled={resolving}
                      type="button"
                    >
                      Approve
                    </button>
                    <button
                      className="interrupt-btn"
                      onClick={() => startEdit(i)}
                      disabled={resolving}
                      type="button"
                    >
                      Edit
                    </button>
                    <button
                      className="interrupt-btn reject"
                      onClick={() => setDecisionAt(i, { type: "reject" })}
                      disabled={resolving}
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
      })}
    </div>
  );
}
