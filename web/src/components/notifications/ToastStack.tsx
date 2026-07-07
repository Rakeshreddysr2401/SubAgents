import { useNotificationsStore } from "../../state/notificationsStore";
import "./ToastStack.css";

const ICONS: Record<string, string> = {
  reminder: "⏰",
  guardian: "🛡️",
  info: "ℹ️",
};

export function ToastStack() {
  const toasts = useNotificationsStore((s) => s.toasts);
  const dismiss = useNotificationsStore((s) => s.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-stack" role="region" aria-label="Notifications">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.kind}`} role="alert">
          <span className="toast-icon">{ICONS[toast.kind] ?? "ℹ️"}</span>
          <div className="toast-content">
            <div className="toast-title">{toast.title}</div>
            <div className="toast-body">{toast.body}</div>
          </div>
          <button className="toast-dismiss" onClick={() => dismiss(toast.id)} aria-label="Dismiss" type="button">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
