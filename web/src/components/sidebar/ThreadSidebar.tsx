import { useState } from "react";
import type { Thread } from "../../api/types";
import { timeAgo } from "../../hooks/useThreads";

interface ThreadSidebarProps {
  threads: Thread[];
  activeThreadId: string;
  open?: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onNewThread: () => void;
}

export function ThreadSidebar({ threads, activeThreadId, open = true, onSelect, onDelete, onRename, onNewThread }: ThreadSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const startEdit = (t: Thread) => {
    setEditingId(t.id);
    setEditValue(t.title);
  };

  const commitEdit = () => {
    if (editingId && editValue.trim()) onRename(editingId, editValue.trim());
    setEditingId(null);
  };

  const [copiedId, setCopiedId] = useState<string | null>(null);
  const copyId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      const el = document.createElement("input");
      el.value = id;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
    setCopiedId(id);
    setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1400);
  };

  return (
    <div className={`history-sidebar${open ? "" : " closed"}`}>
      <button className="new-chat-btn" onClick={onNewThread} type="button">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        New chat
      </button>
      <div className="thread-list">
        {threads.length === 0 && <div className="thread-empty">No conversations yet</div>}
        {threads.map((t) => (
          <div
            key={t.id}
            className={`thread-item${t.id === activeThreadId ? " active" : ""}`}
            title={`${t.title} · ${timeAgo(t.updated_at)}`}
            onClick={() => onSelect(t.id)}
          >
            {editingId === t.id ? (
              <input
                autoFocus
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit();
                  if (e.key === "Escape") setEditingId(null);
                }}
                style={{
                  flex: 1, fontSize: "12.5px", border: "1px solid var(--primary)",
                  borderRadius: 6, padding: "2px 6px", background: "var(--surface)",
                }}
              />
            ) : (
              <span className="thread-title">{t.title}</span>
            )}
            <button
              className={`thread-delete thread-neutral${copiedId === t.id ? " copied" : ""}`}
              onClick={(e) => { e.stopPropagation(); copyId(t.id); }}
              title="Copy conversation id (for LangSmith / logs)"
              type="button"
            >
              {copiedId === t.id ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              )}
            </button>
            <button
              className="thread-delete thread-neutral"
              onClick={(e) => { e.stopPropagation(); startEdit(t); }}
              title="Rename"
              type="button"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
              </svg>
            </button>
            <button
              className="thread-delete"
              onClick={(e) => { e.stopPropagation(); onDelete(t.id); }}
              title="Delete"
              type="button"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6" />
                <path d="M14 11v6" />
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
