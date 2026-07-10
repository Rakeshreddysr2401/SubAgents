import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authFetch } from "../../api/client";
import type { PreflightCheck, PreflightResponse } from "../../api/types";
import { Badge, Button, Card, Page, Spinner } from "../ui";

const CHECK_META: Record<string, { label: string; hint?: string }> = {
  postgres: { label: "Postgres", hint: "docker compose up -d" },
  redis: { label: "Redis", hint: "docker compose up -d" },
  qdrant: { label: "Qdrant", hint: "docker compose up -d" },
  llm: { label: "Language model server" },
  embeddings: { label: "Embeddings model" },
  swiggy: { label: "Swiggy ordering (optional)" },
  frontend: { label: "Web app build" },
};

function CheckRow({ name, check }: { name: string; check: PreflightCheck }) {
  const meta = CHECK_META[name] ?? { label: name };
  const optional = name === "swiggy";
  return (
    <div className="ui-row">
      <span className="ui-row-label">
        {meta.label}
        {check.provider && (
          <span className="ui-row-value mono" style={{ marginLeft: 8, fontWeight: 500 }}>
            {check.provider}{check.model ? `/${check.model}` : ""}
          </span>
        )}
      </span>
      <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
        {check.ok
          ? <Badge kind="ok">ready</Badge>
          : <Badge kind={optional ? "neutral" : "err"}>{optional ? "not set up" : "needs attention"}</Badge>}
        {!check.ok && (check.detail || meta.hint) && (
          <span style={{ fontSize: 11.5, color: "var(--text-muted)", maxWidth: 340, textAlign: "right" }}>
            {check.detail || meta.hint}
          </span>
        )}
      </span>
    </div>
  );
}

export function SetupWizard() {
  const navigate = useNavigate();
  const [result, setResult] = useState<PreflightResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const check = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch("/system/preflight");
      if (!res.ok) throw new Error(`Preflight failed (${res.status})`);
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  return (
    <Page title="System check">
      <Card
        title={result?.ready ? "Everything is ready" : "Let's get you set up"}
        icon={result?.ready
          ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
          : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>}
        sub={result?.ready
          ? "All required services are reachable — the assistant is fully operational."
          : "The assistant checked its dependencies below. Fix anything marked red (the hints say how), then re-check. Configuration lives in the .env file — see .env.example for every option."}
      >
        {loading && !result && <Spinner />}
        {error && <Badge kind="err">{error}</Badge>}
        {result &&
          Object.entries(result.checks).map(([name, checkResult]) => (
            <CheckRow key={name} name={name} check={checkResult} />
          ))}
      </Card>

      {result && !result.checks.llm?.ok && (
        <Card title="Point me at a model server">
          <div className="ui-card-sub">
            This assistant talks to an OpenAI-compatible server (e.g. llama.cpp on a Mac
            mini) or a cloud provider. Edit <code>.env</code> and restart:
          </div>
          <div className="ui-code-hint">{`# self-hosted llama.cpp (recommended)
LLM_PROVIDER=llama_cpp
LLAMA_CPP_BASE_URL=http://your-server.local:8080/v1
SUPERVISOR_MODEL=your-model-name

# ...or a cloud provider
LLM_PROVIDER=openai      # or anthropic | gemini
OPENAI_API_KEY=sk-...`}</div>
        </Card>
      )}

      {result && !result.checks.embeddings?.ok && (
        <Card title="Pull the embedding model">
          <div className="ui-card-sub">
            Memory and document search embed text locally through Ollama:
          </div>
          <div className="ui-code-hint">ollama pull nomic-embed-text</div>
        </Card>
      )}

      <div style={{ display: "flex", gap: 10 }}>
        <Button onClick={check} disabled={loading}>{loading ? "Checking…" : "Re-check"}</Button>
        <Button primary onClick={() => navigate("/")} disabled={!result?.ready}>
          Open the assistant
        </Button>
      </div>
    </Page>
  );
}
