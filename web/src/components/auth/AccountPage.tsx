import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { parseJsonError } from "../../api/client";
import { useAuth } from "../../state/AuthContext";
import "./Auth.css";

export function AccountPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwMsg, setPwMsg] = useState<{ text: string; kind: "success" | "error" } | null>(null);
  const [pwSubmitting, setPwSubmitting] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteMsg, setDeleteMsg] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const submitPasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwSubmitting(true);
    setPwMsg(null);
    try {
      const res = await fetch("/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!res.ok) throw new Error(await parseJsonError(res));
      setPwMsg({ text: "Password updated.", kind: "success" });
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setPwMsg({ text: err instanceof Error ? err.message : String(err), kind: "error" });
    } finally {
      setPwSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    setDeleting(true);
    setDeleteMsg(null);
    try {
      const res = await fetch("/auth/account", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ password: deletePassword }),
      });
      if (!res.ok) throw new Error(await parseJsonError(res));
      await logout();
      navigate("/login", { replace: true });
    } catch (err) {
      setDeleteMsg(err instanceof Error ? err.message : String(err));
      setDeleting(false);
    }
  };

  return (
    <div className="auth-body" style={{ alignItems: "flex-start" }}>
      <div className="account-wrap">
        <div className="account-topbar">
          <Link className="back-link" to="/">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" /></svg>
            Back to chat
          </Link>
        </div>

        <div className="account-card">
          <div className="account-profile-header">
            <div className="account-avatar">{user?.email?.[0]?.toUpperCase() ?? "?"}</div>
            <div>
              <div className="email">{user?.email ?? "Loading…"}</div>
              <div className="sub">Account settings</div>
            </div>
          </div>
        </div>

        <div className="account-card">
          <div className="account-card-header"><h2>Change password</h2></div>
          <form className="auth-form" onSubmit={submitPasswordChange}>
            {pwMsg && <div className={`account-msg ${pwMsg.kind}`}>{pwMsg.text}</div>}
            <div className="auth-field">
              <label>Current password</label>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div className="auth-field">
              <label>New password</label>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <button className="account-btn btn-primary" type="submit" disabled={pwSubmitting}>
              Update password
            </button>
          </form>
        </div>

        <div className="account-card">
          <div className="account-card-header"><h2>Danger zone</h2></div>
          <div className="danger-body">
            <p>Deleting your account permanently removes your profile and all chat history. This cannot be undone.</p>
            <button className="account-btn btn-danger" onClick={() => setDeleteOpen(true)} type="button">
              Delete account
            </button>
          </div>
        </div>
      </div>

      {deleteOpen && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>Delete your account?</h3>
            <p>Enter your password to confirm. All conversations will be permanently deleted.</p>
            <div className="auth-field">
              <input
                type="password"
                placeholder="Password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
              />
            </div>
            {deleteMsg && <div className="account-msg error">{deleteMsg}</div>}
            <div className="modal-actions">
              <button className="account-btn btn-ghost" onClick={() => setDeleteOpen(false)} type="button">Cancel</button>
              <button className="account-btn btn-danger" onClick={confirmDelete} disabled={deleting} type="button">
                Delete forever
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
