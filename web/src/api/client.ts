/**
 * Fetch wrapper with silent access-token refresh on 401.
 * Ports the exact algorithm from static/index.html's authFetch(): on a 401,
 * try POST /auth/refresh once, retry the original request once, else bounce
 * to /login. Cookies are httpOnly so this file never touches token values.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const opts: RequestInit = { ...options, credentials: "include" };
  let res = await fetch(url, opts);
  if (res.status === 401) {
    const refreshed = await fetch("/auth/refresh", { method: "POST", credentials: "include" });
    if (refreshed.ok) {
      res = await fetch(url, opts);
    } else {
      window.location.href = "/login";
      throw new Error("Session expired");
    }
  }
  return res;
}

export async function parseJsonError(res: Response): Promise<string> {
  const data = await res.json().catch(() => ({}) as { detail?: string });
  return data.detail || `HTTP ${res.status}`;
}
