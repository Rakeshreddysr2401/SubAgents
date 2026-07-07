import { useCallback, useEffect, useRef, useState } from "react";

interface CameraPanelProps {
  threadId: string;
}

const CAPTURE_INTERVAL_MS = 2000;

export function CameraPanel({ threadId }: CameraPanelProps) {
  const [active, setActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const connectWS = useCallback(() => {
    wsRef.current?.close();
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    wsRef.current = new WebSocket(`${proto}//${location.host}/ws/frames?thread_id=${threadId || "pending"}`);
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
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    setActive(false);
  }, []);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setActive(true);
      connectWS();
      intervalRef.current = setInterval(captureFrame, CAPTURE_INTERVAL_MS);
    } catch {
      // permission denied/unavailable — the toggle button just stays off
    }
  }, [connectWS, captureFrame]);

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
        <div className={`live-badge${active ? " active" : ""}`}>
          <div className="dot" />
          LIVE
        </div>
      </div>
      <div className="video-viewport">
        <video ref={videoRef} autoPlay playsInline muted className={active ? "active" : ""} />
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
