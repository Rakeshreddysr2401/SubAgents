import { useEffect, useRef, useState } from "react";
import { useVoiceStore } from "../../state/voiceStore";
import "./Composer.css";

interface SpeechRecognitionResultEvent extends Event {
  results: { [index: number]: { [index: number]: { transcript: string } } };
}
interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
}

interface ComposerProps {
  onSend: (text: string) => void;
  sending: boolean;
  alwaysSpeak: boolean;
  onToggleAlwaysSpeak: () => void;
  /** Time travel: pre-filled text of the message being edited & resent. */
  rewindDraft?: string | null;
  onCancelRewind?: () => void;
}

const SpeechRecognitionCtor: (new () => SpeechRecognitionLike) | undefined =
  (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike }).SpeechRecognition ??
  (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition;

export function Composer({
  onSend, sending, alwaysSpeak, onToggleAlwaysSpeak, rewindDraft, onCancelRewind,
}: ComposerProps) {
  const [value, setValue] = useState("");

  useEffect(() => {
    if (rewindDraft != null) {
      setValue(rewindDraft);
      textareaRef.current?.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rewindDraft]);
  const listening = useVoiceStore((s) => s.listening);
  const setListening = useVoiceStore((s) => s.setListening);
  const wakeSignal = useVoiceStore((s) => s.wakeSignal);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    if (!SpeechRecognitionCtor) return;
    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onstart = () => setListening(true);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setValue(transcript);
      onSend(transcript);
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    // onSend is stable across the composer's lifetime in ChatView; recreating
    // the recognition object per-keystroke would drop in-flight listening state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Wake-word detection (WakeWordIndicator, via /events) bumps wakeSignal to
  // start listening remotely, mirroring index.html's setupEventSource().
  useEffect(() => {
    if (wakeSignal > 0 && !listening) recognitionRef.current?.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wakeSignal]);

  const submit = () => {
    const text = value.trim();
    if (!text || sending) return;
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    onSend(text);
  };

  const toggleSpeech = () => {
    if (!recognitionRef.current) return;
    if (listening) recognitionRef.current.stop();
    else recognitionRef.current.start();
  };

  return (
    <div className="input-area">
      {rewindDraft != null && (
        <div className="rewind-banner">
          <span>Editing an earlier message — sending will rewind the conversation to that point.</span>
          <button onClick={onCancelRewind} type="button">Cancel</button>
        </div>
      )}
      <div className="input-wrapper">
        {SpeechRecognitionCtor && (
          <button
            className={`mic-btn${listening ? " active" : ""}`}
            onClick={toggleSpeech}
            title="Voice input"
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          </button>
        )}
        <textarea
          ref={textareaRef}
          className="chat-input"
          rows={1}
          placeholder="Type or speak..."
          autoFocus
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            const el = e.target;
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 120) + "px";
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="send-btn" onClick={submit} disabled={sending} type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
      <div className="input-hint">
        Enter to send &middot; Shift+Enter for new line &middot;{" "}
        <span
          onClick={onToggleAlwaysSpeak}
          style={{ cursor: "pointer", fontWeight: 600, color: alwaysSpeak ? "var(--green)" : undefined }}
        >
          voice replies: {alwaysSpeak ? "on" : "off"}
        </span>
      </div>
    </div>
  );
}
