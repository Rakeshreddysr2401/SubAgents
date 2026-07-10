import type { Todo } from "../../api/types";
import "./ActivityCards.css";

function StatusIcon({ status }: { status: Todo["status"] }) {
  if (status === "completed") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (status === "in_progress") {
    return <span className="plan-spinner" />;
  }
  return <span className="plan-dot" />;
}

export function PlanCard({ todos }: { todos: Todo[] }) {
  if (todos.length === 0) return null;
  return (
    <div className="plan-card">
      <div className="plan-card-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
        Plan
      </div>
      {todos.map((todo, i) => (
        <div key={i} className={`plan-item plan-item-${todo.status}`}>
          <span className="plan-item-icon">
            <StatusIcon status={todo.status} />
          </span>
          <span className="plan-item-text">{todo.content}</span>
        </div>
      ))}
    </div>
  );
}
