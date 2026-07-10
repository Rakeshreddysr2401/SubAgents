import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "../../api/client";
import { useEventsStore } from "../../state/eventsStore";

interface CameraPanelProps {
  threadId: string;
}

const CAPTURE_INTERVAL_MS = 2000;
const RETRY_DELAYS_MS = [1000, 2000, 4000];

export function CameraPanel({ threadId }: CameraPanelProps) {
  const [active, setActive] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeRef = useRef(false);
  const attemptRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const guardianEnabled = useEventsStore((s) => s.guardianEnabled);
  const setGuardianEnabled = useEventsStore((s) => s.setGuardianEnabled);

  // Pick up guardian state on mount (it survives page reloads server-side).
  useEffect(() => {
    authFetch("/guardian/status")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setGuardianEnabled(Boolean(data.enabled));
      })
      .catch(() => {});
  }, [setGuardianEnabled]);

  const connectWS = useCallback(() => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    retryTimerRef.current = null;
    if (wsRef.current) {
      // Detach handlers so closing the old socket doesn't schedule a reconnect
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
    }
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/frames?thread_id=${threadId || "pending"}`);
    ws.onopen = () => {
      attemptRef.current = 0;
      setWsConnected(true);
    };
    ws.onclose = () => {
      setWsConnected(false);
      // Auto-reconnect while the camera is still on (backend restarts, network
      // blips) — otherwise the UI showed LIVE over a dead socket forever.
      if (activeRef.current && wsRef.current === ws) {
        const delay = RETRY_DELAYS_MS[Math.min(attemptRef.current, RETRY_DELAYS_MS.length - 1)];
        attemptRef.current += 1;
        retryTimerRef.current = setTimeout(connectWS, delay);
      }
    };
    wsRef.current = ws;
  }, [threadId]);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx?.drawImage(video, 0, 0);
    const b64 = canvas.toDataURL("image/jpeg", 0.6).split(",")[1];
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(b64);
  }, []);

  const stopCamera = useCallback(() => {
    activeRef.current = false;
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    retryTimerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
    }
    wsRef.current = null;
    setWsConnected(false);
    setActive(false);
  }, []);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      activeRef.current = true;
      setActive(true);
      connectWS();
      intervalRef.current = setInterval(captureFrame, CAPTURE_INTERVAL_MS);
    } catch {
      // permission denied/unavailable — the toggle button just stays off
    }
  }, [connectWS, captureFrame]);

  const toggleGuardian = useCallback(async () => {
    if (guardianEnabled) {
      setGuardianEnabled(false);
      await authFetch("/guardian/disable", { method: "POST" }).catch(() => {});
      return;
    }
    // Guardian needs frames — auto-start the camera if it's off.
    if (!activeRef.current) await startCamera();
    setGuardianEnabled(true);
    await authFetch("/guardian/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: threadId || "pending" }),
    }).catch(() => setGuardianEnabled(false));
  }, [guardianEnabled, setGuardianEnabled, startCamera, threadId]);

  // Frames must follow the active thread — reconnect the WS on thread change
  // (ports index.html's reconnectFrameWS(), called on newThread/selectThread).
  useEffect(() => {
    if (active) connectWS();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  useEffect(() => stopCamera, [stopCamera]);

  return (
    <div className="video-card">
      <div className="video-card-header">
        <div className="video-card-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="23 7 16 12 23 17 23 7" />
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
          </svg>
          Camera
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            className={`cam-btn guardian-btn${guardianEnabled ? " on" : ""}`}
            onClick={toggleGuardian}
            title={guardianEnabled ? "Guardian mode is ON — click to disable" : "Enable guardian mode (watches the camera and alerts you)"}
            type="button"
            style={{ width: 26, height: 26, padding: 4 }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </button>
          <div className={`live-badge${active && wsConnected ? " active" : ""}`}>
            <div className="dot" />
            {active && !wsConnected ? "RECONNECTING" : "LIVE"}
          </div>
        </div>
      </div>
      <div className="video-viewport">
        <video ref={videoRef} autoPlay playsInline muted className={active ? "active" : ""} />
        {/* Offscreen canvas: captureFrame() draws the video here to JPEG-encode
            each frame before sending it over the WS. Without this element
            canvasRef stays null and no frames are ever sent. */}
        <canvas ref={canvasRef} style={{ display: "none" }} />
        {!active && (
          <div className="video-placeholder">
            <div className="icon-ring">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
            </div>
            <span>Enable camera to start</span>
          </div>
        )}
        <div className="video-controls">
          <button
            className={`cam-btn${active ? " on" : ""}`}
            onClick={active ? stopCamera : startCamera}
            title="Toggle camera"
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
