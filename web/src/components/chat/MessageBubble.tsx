import { useEffect, useRef } from "react";
import { addCopyButtons, renderMarkdown } from "../../utils/markdown";
import { ToolActivityCard } from "./ToolActivityCard";
import type { ToolActivityItem } from "../../state/chatStream";

export interface ChatMessage {
  id: string;
  role: "user" | "bot";
  content: string;
  thinking?: boolean;
  toolActivity?: ToolActivityItem[];
}

export function MessageBubble({ role, content, thinking, toolActivity }: ChatMessage) {
  const mdRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (role === "bot" && mdRef.current && !thinking) {
      addCopyButtons(mdRef.current);
    }
  }, [role, content, thinking]);

  return (
    <div className={`message ${role}`}>
      <div className="avatar">{role === "user" ? "U" : "S"}</div>
      {role === "user" ? (
        <div className="bubble">{content}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {toolActivity && toolActivity.length > 0 && <ToolActivityCard items={toolActivity} />}
          <div className={`bubble${thinking ? " thinking-active" : ""}`}>
            {thinking ? (
              <div className="thinking-label">
                Thinking
                <span className="tdots"><span /><span /><span /></span>
              </div>
            ) : (
              <div
                ref={mdRef}
                className="md-content"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
