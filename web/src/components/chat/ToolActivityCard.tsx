import type { ToolActivityItem } from "../../state/chatStream";

function friendlyToolName(name: string): string {
  return name.replace(/_/g, " ");
}

export function ToolActivityCard({ items }: { items: ToolActivityItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="tool-activity-card">
      {items.map((item) => (
        <div key={item.id} className={`tool-activity-row${item.status === "done" ? " done" : ""}`}>
          <span className="tool-activity-icon">
            {item.status === "calling" ? (
              <span className="tool-activity-spinner" />
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
          </span>
          <span className="tool-activity-text">
            {item.status === "calling" ? `Calling ${friendlyToolName(item.name)}…` : friendlyToolName(item.name)}
          </span>
        </div>
      ))}
    </div>
  );
}
