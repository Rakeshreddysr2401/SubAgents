import { useState } from "react";
import type { ToolActivityItem } from "../../state/chatStream";
import "./ActivityCards.css";

export function friendlyToolName(name: string): string {
  return name.replace(/_/g, " ");
}

/** Collapsed one-line trail of the steps a reply took ("✓ 2 steps"),
 * expandable on tap. Lives INSIDE the message bubble — no extra cards, no
 * extra avatars. The live in-flight status is rendered by MessageBubble's
 * thinking line instead. */
export function ActivityTrail({ items }: { items: ToolActivityItem[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;

  const label = items.length === 1
    ? friendlyToolName(items[0].name)
    : `${items.length} steps`;

  return (
    <div className="activity-trail">
      <button
        className="activity-trail-toggle"
        onClick={() => setOpen((v) => !v)}
        type="button"
        aria-expanded={open}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
        {label}
        <svg
          className={`activity-trail-chevron${open ? " open" : ""}`}
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div className="activity-trail-list">
          {items.map((item) => (
            <div key={item.id} className="activity-trail-row">
              <span className="activity-trail-agent">{item.agent}</span>
              {friendlyToolName(item.name)}
              {item.status === "calling" && "…"}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
