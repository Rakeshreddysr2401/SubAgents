import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../../api/client";
import { useThemeStore } from "../../state/themeStore";
import { Badge, Button, Card, Page, Row, Spinner } from "../ui";

interface LlmStatus {
  provider: string;
  model: string;
  base_url: string;
  primary_available: boolean;
  primary_retry_in_s: number;
  fallback: string | null;
  fallback_used_total: number;
  slots: Record<string, number> | null;
}

interface McpStatus {
  providers: Record<string, { tools: number; ok: boolean }>;
  tokens: Record<string, { source: string; days_left: number | null; stale: boolean }>;
}

interface StatusResponse {
  llm: LlmStatus;
  mcp: McpStatus;
  postgres: { ok: boolean };
  redis: { ok: boolean };
  qdrant: { ok: boolean };
  mem0: boolean;
}

export function SettingsPage() {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch("/status");
      if (!res.ok) throw new Error(`Status check failed (${res.status})`);
      setStatus(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const llm = status?.llm;
  const swiggy = status?.mcp.tokens.swiggy;

  return (
    <Page title="Settings">
      <Card
        title="Appearance"
        icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" /></svg>}
      >
        <Row label="Theme">
          <span className="ui-segment">
            <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")} type="button">Light</button>
            <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")} type="button">Dark</button>
          </span>
        </Row>
      </Card>

      <Card
        title="Language model"
        icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" /></svg>}
        sub="Provider health for the model server this assistant talks to. Configure providers in .env (see .env.example)."
      >
        {loading && <Spinner />}
        {error && <Badge kind="err">{error}</Badge>}
        {llm && (
          <>
            <Row label="Provider / model">
              <span className="ui-row-value mono">{llm.provider} / {llm.model}</span>
            </Row>
            {llm.base_url && (
              <Row label="Endpoint"><span className="ui-row-value mono">{llm.base_url}</span></Row>
            )}
            <Row label="Primary status">
              {llm.primary_available
                ? <Badge kind="ok">up</Badge>
                : <Badge kind="err">cooling down — retry in {Math.ceil(llm.primary_retry_in_s)}s</Badge>}
            </Row>
            <Row label="Cloud fallback">
              {llm.fallback
                ? <Badge kind="ok">{llm.fallback} · used {llm.fallback_used_total}×</Badge>
                : <Badge kind="neutral">not configured</Badge>}
            </Row>
            {llm.slots && Object.keys(llm.slots).length > 0 && (
              <Row label="KV-cache slots">
                <span className="ui-row-value mono">
                  {Object.entries(llm.slots).map(([a, s]) => `${a}:${s}`).join("  ")}
                </span>
              </Row>
            )}
          </>
        )}
      </Card>

      <Card
        title="Integrations"
        icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></svg>}
        sub="Swiggy ordering (food, groceries, dine-out) connects through your own Swiggy login."
      >
        {status && (
          <>
            {Object.entries(status.mcp.providers).map(([name, p]) => (
              <Row key={name} label={name.replace("swiggy_", "Swiggy ")}>
                {p.ok
                  ? <Badge kind="ok">{p.tools} tools</Badge>
                  : <Badge kind="neutral">off</Badge>}
              </Row>
            ))}
            <Row label="Swiggy login">
              {swiggy?.stale ? (
                <Badge kind="err">expired — re-run the login script</Badge>
              ) : swiggy?.source === "none" ? (
                <Badge kind="neutral">not connected</Badge>
              ) : (
                <Badge kind="ok">
                  {swiggy?.days_left != null ? `${swiggy.days_left} days left` : "connected"}
                </Badge>
              )}
            </Row>
            {(swiggy?.source === "none" || swiggy?.stale) && (
              <div className="ui-code-hint">uv run python scripts/swiggy_login.py --verify</div>
            )}
          </>
        )}
      </Card>

      <Card
        title="Services"
        icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" /></svg>}
      >
        {status && (
          <>
            <Row label="Postgres">{status.postgres.ok ? <Badge kind="ok">connected</Badge> : <Badge kind="err">down</Badge>}</Row>
            <Row label="Redis">{status.redis.ok ? <Badge kind="ok">connected</Badge> : <Badge kind="err">down</Badge>}</Row>
            <Row label="Qdrant">{status.qdrant.ok ? <Badge kind="ok">connected</Badge> : <Badge kind="err">down</Badge>}</Row>
            <Row label="Long-term memory (Mem0)">{status.mem0 ? <Badge kind="ok">active</Badge> : <Badge kind="warn">disabled</Badge>}</Row>
          </>
        )}
      </Card>

      <div style={{ display: "flex", gap: 10 }}>
        <Button onClick={load} disabled={loading}>
          {loading ? "Checking…" : "Re-check"}
        </Button>
        <Button onClick={() => (window.location.href = "/account")}>Account settings</Button>
      </div>
    </Page>
  );
}
