import { useState } from "react";

/** Copyable conversation id — the LangGraph thread_id, which is also the key
 * LangSmith traces carry in metadata (`thread_id`). Click to copy the full
 * id; the chip shows a short prefix and a copied✓ confirmation. */
export function ThreadIdChip({ threadId }: { threadId: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(threadId);
    } catch {
      // Clipboard API blocked (insecure context) — fall back to a temp input.
      const el = document.createElement("input");
      el.value = threadId;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  return (
    <button
      className={`thread-id-chip${copied ? " copied" : ""}`}
      onClick={copy}
      title={`Conversation id: ${threadId}\nClick to copy (use it to find this trace in LangSmith)`}
      aria-label="Copy conversation id"
      type="button"
    >
      {copied ? (
        <>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          copied
        </>
      ) : (
        <>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          {threadId.slice(0, 8)}
        </>
      )}
    </button>
  );
}
