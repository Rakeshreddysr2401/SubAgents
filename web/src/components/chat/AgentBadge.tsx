const AGENT_LABELS: Record<string, string> = {
  conversation: "Conversation",
  swiggy: "Swiggy",
  tracker: "Tracker",
  planner: "Planner",
};

export function AgentBadge({ agent }: { agent: string }) {
  return (
    <span className="header-pill agent-badge" title={`Active agent: ${agent}`}>
      <span className="agent-badge-dot" />
      {AGENT_LABELS[agent] ?? agent}
    </span>
  );
}
