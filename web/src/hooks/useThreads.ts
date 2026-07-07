import { useCallback, useState } from "react";
import { authFetch } from "../api/client";
import type { Thread } from "../api/types";

export function useThreads() {
  const [threads, setThreads] = useState<Thread[]>([]);

  const loadThreads = useCallback(async () => {
    try {
      const res = await authFetch("/threads");
      if (!res.ok) return;
      setThreads(await res.json());
    } catch {
      // non-fatal, mirrors index.html's loadThreads()
    }
  }, []);

  const renameThread = useCallback(async (id: string, title: string) => {
    const res = await authFetch(`/threads/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (res.ok) await loadThreads();
    return res.ok;
  }, [loadThreads]);

  const deleteThread = useCallback(async (id: string) => {
    await authFetch(`/threads/${id}`, { method: "DELETE" });
    await loadThreads();
  }, [loadThreads]);

  return { threads, loadThreads, renameThread, deleteThread };
}

export function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
