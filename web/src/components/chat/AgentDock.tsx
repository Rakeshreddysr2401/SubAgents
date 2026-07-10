/** The swarm at a glance: one chip per agent, the active one lit in its
 * identity color with its name expanded. Pure display — activeAgent comes
 * from the chat stream store via ChatView. */

import type { ReactElement } from "react";

interface AgentMeta {
  label: string;
  cssVar: string; // per-agent identity color token (tokens.css)
  icon: ReactElement;
}

const S = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const AGENT_META: Record<string, AgentMeta> = {
  conversation: {
    label: "Chat", cssVar: "--agent-conversation",
    icon: <svg viewBox="0 0 24 24" {...S}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>,
  },
  swiggy: {
    label: "Food", cssVar: "--agent-swiggy",
    icon: <svg viewBox="0 0 24 24" {...S}><path d="M3 11h18l-1.5 8.5a2 2 0 0 1-2 1.5h-11a2 2 0 0 1-2-1.5z" /><path d="M12 3a7 7 0 0 1 7 7H5a7 7 0 0 1 7-7z" /></svg>,
  },
  instamart: {
    label: "Grocery", cssVar: "--agent-instamart",
    icon: <svg viewBox="0 0 24 24" {...S}><circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" /><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" /></svg>,
  },
  dineout: {
    label: "Dine out", cssVar: "--agent-dineout",
    icon: <svg viewBox="0 0 24 24" {...S}><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2" /><line x1="7" y1="2" x2="7" y2="22" /><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7" /></svg>,
  },
  tracker: {
    label: "Tracking", cssVar: "--agent-tracker",
    icon: <svg viewBox="0 0 24 24" {...S}><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>,
  },
  planner: {
    label: "Planner", cssVar: "--agent-planner",
    icon: <svg viewBox="0 0 24 24" {...S}><rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /><path d="m9 16 2 2 4-4" /></svg>,
  },
};

export function AgentDock({ activeAgent }: { activeAgent: string }) {
  return (
    <div className="agent-dock" role="status" aria-label={`Active agent: ${activeAgent}`}>
      {Object.entries(AGENT_META).map(([name, meta]) => {
        const active = name === activeAgent;
        return (
          <span
            key={name}
            className={`agent-dock-item${active ? " active" : ""}`}
            style={{ "--agent-color": `var(${meta.cssVar})` } as React.CSSProperties}
            title={meta.label}
          >
            {meta.icon}
            <span className="agent-dock-name">{meta.label}</span>
          </span>
        );
      })}
    </div>
  );
}
