import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import "./ui.css";

/** Full-height page shell with a centered column + back-to-chat header. */
export function Page({ title, children }: { title: string; children: ReactNode }) {
  const navigate = useNavigate();
  return (
    <div className="ui-page">
      <div className="ui-page-inner">
        <div className="ui-page-header">
          <button className="ui-back-link" onClick={() => navigate("/")} type="button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
            </svg>
            Chat
          </button>
          <h1>{title}</h1>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Card({ title, icon, sub, children }: {
  title: string;
  icon?: ReactNode;
  sub?: string;
  children?: ReactNode;
}) {
  return (
    <div className="ui-card">
      <div className="ui-card-title">{icon}{title}</div>
      {sub && <div className="ui-card-sub">{sub}</div>}
      {children}
    </div>
  );
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="ui-row">
      <span className="ui-row-label">{label}</span>
      <span className="ui-row-value">{children}</span>
    </div>
  );
}

export type BadgeKind = "ok" | "warn" | "err" | "neutral";

export function Badge({ kind, children }: { kind: BadgeKind; children: ReactNode }) {
  return <span className={`ui-badge ${kind}`}>{children}</span>;
}

export function Spinner() {
  return <span className="ui-spinner" aria-label="Loading" />;
}

export function Button({ children, onClick, primary, disabled, type = "button" }: {
  children: ReactNode;
  onClick?: () => void;
  primary?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      className={`ui-btn${primary ? " primary" : ""}`}
      onClick={onClick}
      disabled={disabled}
      type={type}
    >
      {children}
    </button>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="ui-empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      {message}
    </div>
  );
}
