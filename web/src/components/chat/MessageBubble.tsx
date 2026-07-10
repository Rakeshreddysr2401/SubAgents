import { useEffect, useRef } from "react";
import { addCopyButtons, renderMarkdown } from "../../utils/markdown";
import { ToolActivityCard } from "./ToolActivityCard";
import type { ToolActivityItem } from "../../state/chatStream";
import "./Messages.css";

export interface ChatMessage {
  id: string;
  role: "user" | "bot";
  content: string;
  thinking?: boolean;
  /** Live progress line from a long-running tool (progress SSE event). */
  progressText?: string;
  toolActivity?: ToolActivityItem[];
}

interface MessageBubbleProps extends ChatMessage {
  /** "Edit & resend from here" (time travel) — only offered on user messages. */
  onRewind?: () => void;
}

export function MessageBubble({ role, content, thinking, progressText, toolActivity, onRewind }: MessageBubbleProps) {
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
        <>
          {onRewind && (
            <button
              className="msg-rewind"
              onClick={onRewind}
              title="Edit & resend from here"
              aria-label="Edit and resend from this message"
              type="button"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="1 4 1 10 7 10" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
            </button>
          )}
          <div className="bubble">{content}</div>
        </>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {toolActivity && toolActivity.length > 0 && <ToolActivityCard items={toolActivity} />}
          <div className={`bubble${thinking ? " thinking-active" : ""}`}>
            {thinking ? (
              <div className="thinking-label">
                {progressText || "Thinking"}
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
