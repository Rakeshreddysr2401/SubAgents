import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { parseJsonError } from "../../api/client";
import { useAuth } from "../../state/auth";
import "./Auth.css";

type Mode = "login" | "signup";

export function LoginPage() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();

  if (user) {
    navigate("/", { replace: true });
    return null;
  }

  const isLogin = mode === "login";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (mode === "signup" && password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (!res.ok) throw new Error(await parseJsonError(res));
      await refreshUser();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-body">
      <div className="auth-card">
        <div className="auth-card-header">
          <div className="logo-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h1>SubAgents</h1>
          <p>Your multi-agent AI assistant</p>
        </div>

        <div className="auth-tabs">
          <div className={`auth-tab${isLogin ? " active" : ""}`} onClick={() => setMode("login")}>Sign in</div>
          <div className={`auth-tab${!isLogin ? " active" : ""}`} onClick={() => setMode("signup")}>Create account</div>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="auth-field">
            <label>Email</label>
            <input
              type="email"
              autoComplete="email"
              required
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="auth-field">
            <label>Password</label>
            <input
              type="password"
              autoComplete={isLogin ? "current-password" : "new-password"}
              required
              minLength={8}
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {!isLogin && <span className="auth-hint">At least 8 characters</span>}
          </div>
          <button className="auth-submit" type="submit" disabled={submitting}>
            {submitting ? (isLogin ? "Signing in…" : "Creating account…") : isLogin ? "Sign in" : "Create account"}
          </button>
          <div className="auth-switch-hint">
            {isLogin ? (
              <>Don't have an account? <a onClick={() => setMode("signup")}>Create one</a></>
            ) : (
              <>Already have an account? <a onClick={() => setMode("login")}>Sign in</a></>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
