import { useEffect } from "react";
import { authFetch } from "../api/client";
import { speak } from "../lib/tts";
import { useEventsStore } from "../state/eventsStore";
import { useMusicStore } from "../state/musicStore";
import { useNotificationsStore } from "../state/notificationsStore";
import { useVoiceStore } from "../state/voiceStore";

const RETRY_DELAYS_MS = [1000, 2000, 4000];

/** Headless owner of the single /events EventSource. Dispatches server-push
 * events (wake word, reminders, shopping, music, guardian) into the zustand
 * stores. All payloads are JSON with a "type" key; unknown types are ignored
 * so new server event types are additive. */
export function EventsBridge() {
  const setConnected = useEventsStore((s) => s.setConnected);
  const bumpReminders = useEventsStore((s) => s.bumpReminders);
  const bumpShopping = useEventsStore((s) => s.bumpShopping);
  const setGuardianEnabled = useEventsStore((s) => s.setGuardianEnabled);
  const triggerWake = useVoiceStore((s) => s.triggerWake);
  const pushToast = useNotificationsStore((s) => s.push);
  const playMusic = useMusicStore((s) => s.play);
  const stopMusic = useMusicStore((s) => s.stop);

  useEffect(() => {
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let stopped = false;

    function handleEvent(data: string) {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(data);
      } catch {
        return;
      }
      switch (parsed.type) {
        case "start_voice":
          triggerWake();
          break;
        case "reminder": {
          const reminder = parsed.reminder as { text?: string } | undefined;
          const text = reminder?.text ?? "";
          pushToast({ kind: "reminder", title: "Reminder", body: text, persistent: true });
          speak(`Reminder: ${text}`);
          bumpReminders();
          break;
        }
        case "reminders_updated":
          bumpReminders();
          break;
        case "shopping_updated":
          bumpShopping();
          break;
        case "music":
          if (parsed.action === "play" && typeof parsed.url === "string") {
            playMusic({ url: parsed.url, station: String(parsed.station ?? "Radio") });
          } else if (parsed.action === "stop") {
            stopMusic();
          }
          break;
        case "guardian_alert": {
          const message = String(parsed.message ?? "Something needs your attention.");
          pushToast({ kind: "guardian", title: "Guardian alert", body: message, persistent: true });
          speak(`Guardian alert: ${message}`);
          break;
        }
        case "guardian_status": {
          if (parsed.status === "enabled") setGuardianEnabled(true);
          if (parsed.status === "disabled") setGuardianEnabled(false);
          if (parsed.status === "no_frame") {
            pushToast({
              kind: "info",
              title: "Guardian",
              body: "No camera feed — turn the camera on so guardian mode can watch.",
              persistent: false,
            });
          }
          break;
        }
        default:
          break;
      }
    }

    async function reconnect() {
      // The access token may have expired since connect — authFetch silently
      // refreshes it, so the next EventSource handshake carries a valid cookie.
      try {
        await authFetch("/auth/me");
      } catch {
        // authFetch redirects to /login on hard failure; nothing to do here.
      }
      if (!stopped) connect();
    }

    function connect() {
      source = new EventSource("/events");
      source.onopen = () => {
        setConnected(true);
        attempt = 0;
      };
      source.onmessage = (event) => handleEvent(event.data);
      source.onerror = () => {
        setConnected(false);
        source?.close();
        if (stopped) return;
        const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
        attempt += 1;
        retryTimer = setTimeout(reconnect, delay);
      };
    }
    connect();

    return () => {
      stopped = true;
      source?.close();
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [setConnected, bumpReminders, bumpShopping, setGuardianEnabled, triggerWake, pushToast, playMusic, stopMusic]);

  return null;
}
