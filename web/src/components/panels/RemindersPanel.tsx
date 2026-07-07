import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../../api/client";
import { useEventsStore } from "../../state/eventsStore";
import "./Panels.css";

interface Reminder {
  id: string;
  text: string;
  due_at: string;
  status: "pending" | "fired" | "cancelled";
}

function relativeDue(dueAt: string): string {
  const diffMs = new Date(dueAt).getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const minutes = Math.round(abs / 60000);
  const label =
    minutes < 1 ? "under a minute" :
    minutes < 60 ? `${minutes} min` :
    minutes < 60 * 24 ? `${Math.round(minutes / 60)} h` :
    `${Math.round(minutes / (60 * 24))} d`;
  return diffMs >= 0 ? `in ${label}` : `${label} ago`;
}

export function RemindersPanel() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const remindersBump = useEventsStore((s) => s.remindersBump);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch("/reminders");
      if (res.ok) setReminders(await res.json());
    } catch {
      // transient — the next bump/refetch will recover
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, remindersBump]);

  const cancel = useCallback(async (id: string) => {
    await authFetch(`/reminders/${id}`, { method: "DELETE" }).catch(() => {});
    refresh();
  }, [refresh]);

  const pending = reminders.filter((r) => r.status === "pending");
  const past = reminders.filter((r) => r.status !== "pending").slice(0, 5);

  return (
    <div className="tools-card panel-card">
      <div className="tools-card-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="13" r="8" />
          <path d="M12 9v4l2 2" />
          <path d="M5 3L2 6" />
          <path d="M19 3l3 3" />
        </svg>
        Reminders
      </div>
      <div className="panel-body">
        {pending.length === 0 && past.length === 0 && (
          <div className="panel-empty">No reminders — try “remind me in 10 minutes to stretch”.</div>
        )}
        {pending.map((r) => (
          <div key={r.id} className="panel-row">
            <div className="panel-row-main">
              <span className="panel-row-title">{r.text}</span>
              <span className="panel-row-sub">
                {relativeDue(r.due_at)} · {new Date(r.due_at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
            <button className="panel-row-action" onClick={() => cancel(r.id)} title="Cancel reminder" type="button">
              ×
            </button>
          </div>
        ))}
        {past.length > 0 && (
          <>
            <div className="panel-subheader">Past</div>
            {past.map((r) => (
              <div key={r.id} className="panel-row muted">
                <div className="panel-row-main">
                  <span className="panel-row-title">{r.text}</span>
                  <span className="panel-row-sub">{r.status} · {relativeDue(r.due_at)}</span>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
