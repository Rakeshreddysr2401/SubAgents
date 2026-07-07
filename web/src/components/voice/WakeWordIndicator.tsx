import { useEffect, useState } from "react";
import { useVoiceStore } from "../../state/voiceStore";

const RETRY_DELAYS_MS = [1000, 2000, 4000];

export function WakeWordIndicator() {
  const listening = useVoiceStore((s) => s.listening);
  const triggerWake = useVoiceStore((s) => s.triggerWake);
  const [connected, setConnected] = useState(false);
  const [justTriggered, setJustTriggered] = useState(false);

  useEffect(() => {
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let stopped = false;

    function connect() {
      source = new EventSource("/events");
      source.onopen = () => {
        setConnected(true);
        attempt = 0;
      };
      source.onmessage = (event) => {
        if (event.data === "start_voice") {
          triggerWake();
          setJustTriggered(true);
          setTimeout(() => setJustTriggered(false), 3000);
        }
      };
      // Mirrors index.html's setupEventSource(): reconnect with backoff
      // instead of leaving the wake-word channel dead after a drop.
      source.onerror = () => {
        setConnected(false);
        source?.close();
        if (stopped) return;
        const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
        attempt += 1;
        retryTimer = setTimeout(connect, delay);
      };
    }
    connect();

    return () => {
      stopped = true;
      source?.close();
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [triggerWake]);

  const active = listening || justTriggered;
  const label = listening ? "Listening…" : justTriggered ? "Wake word detected" : connected ? "Wake word ready" : "Reconnecting…";

  return (
    <span className={`header-pill wake-word-indicator${connected ? " connected" : ""}${active ? " active" : ""}`}>
      <span className="wake-word-dot" />
      {label}
    </span>
  );
}
