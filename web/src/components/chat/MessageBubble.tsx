import { useEffect, useRef } from "react";
import { addCopyButtons, renderMarkdown } from "../../utils/markdown";
import { ActivityTrail, friendlyToolName } from "./ToolActivityCard";
import type { ToolActivityItem } from "../../state/chatStream";
import "./Messages.css";

export interface ChatMessage {
  id: string;
  role: "user" | "bot";
  content: string;
  thinking?: boolean;
  /** Live progress line from a long-running tool (writer/custom stream). */
  progressText?: string;
  toolActivity?: ToolActivityItem[];
}

interface MessageBubbleProps extends ChatMessage {
  /** "Edit & resend from here" (time travel) — only offered on user messages. */
  onRewind?: () => void;
}

/** What the single in-bubble status line should say while the reply is being
 * worked on. Priority: a specific progress line pushed by the tool itself
 * (LangGraph writer channel) > the tool currently running > the last
 * finished step > plain "Thinking". */
function statusText(progressText: string | undefined, toolActivity: ToolActivityItem[] | undefined): string {
  if (progressText) return progressText;
  const running = toolActivity?.filter((t) => t.status === "calling") ?? [];
  if (running.length > 0) return `${friendlyToolName(running[running.length - 1].name)}…`;
  const done = toolActivity?.filter((t) => t.status === "done") ?? [];
  if (done.length > 0) return `${friendlyToolName(done[done.length - 1].name)} ✓`;
  return "Thinking";
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
      <div className="avatar">
        {role === "user" ? "U" : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-label="Assistant">
            <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
            <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" />
          </svg>
        )}
      </div>
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
        // ONE bubble per reply: while working it carries the live status
        // line; once text arrives the steps collapse into a tiny trail above
        // the answer. No stacked cards, no duplicate avatars.
        <div className={`bubble${thinking ? " thinking-active" : ""}`}>
          {thinking ? (
            <div className="thinking-label">
              {statusText(progressText, toolActivity)}
              <span className="tdots"><span /><span /><span /></span>
            </div>
          ) : (
            <>
              {toolActivity && toolActivity.length > 0 && <ActivityTrail items={toolActivity} />}
              <div
                ref={mdRef}
                className="md-content"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
}
