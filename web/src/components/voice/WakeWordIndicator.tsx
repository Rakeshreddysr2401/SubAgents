import { useEffect, useState } from "react";
import { useEventsStore } from "../../state/eventsStore";
import { useVoiceStore } from "../../state/voiceStore";

/** Pure display — the /events subscription lives in EventsBridge; this pill
 * just reflects connection + listening state. */
export function WakeWordIndicator() {
  const listening = useVoiceStore((s) => s.listening);
  const wakeSignal = useVoiceStore((s) => s.wakeSignal);
  const connected = useEventsStore((s) => s.connected);
  const [justTriggered, setJustTriggered] = useState(false);

  useEffect(() => {
    if (wakeSignal === 0) return;
    setJustTriggered(true);
    const timer = setTimeout(() => setJustTriggered(false), 3000);
    return () => clearTimeout(timer);
  }, [wakeSignal]);

  const active = listening || justTriggered;
  const label = listening ? "Listening…" : justTriggered ? "Wake word detected" : connected ? "Wake word ready" : "Reconnecting…";

  return (
    <span className={`header-pill wake-word-indicator${connected ? " connected" : ""}${active ? " active" : ""}`}>
      <span className="wake-word-dot" />
      {label}
    </span>
  );
}
