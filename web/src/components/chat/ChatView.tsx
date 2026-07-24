import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authFetch } from "../../api/client";
import { resumeChat, streamChat } from "../../api/stream";
import type {
  ChatEvent,
  PreflightResponse,
  ResumeDecision,
  ThreadCheckpoint,
  ThreadMessagesResponse,
  Todo,
} from "../../api/types";
import { useAuth } from "../../state/auth";
import { useChatStream } from "../../state/chatStream";
import { useThreads } from "../../hooks/useThreads";
import { ThreadSidebar } from "../sidebar/ThreadSidebar";
import { MessageBubble, type ChatMessage } from "./MessageBubble";
import { AgentDock } from "./AgentDock";
import { ThreadIdChip } from "./ThreadIdChip";
import { InterruptCard } from "./InterruptCard";
import { PlanCard } from "./PlanCard";
import { Composer } from "./Composer";
import { CameraPanel } from "../vision/CameraPanel";
import { WakeWordIndicator } from "../voice/WakeWordIndicator";
import { VoiceWaveform } from "../voice/VoiceWaveform";
import { EventsBridge } from "../EventsBridge";
import { ToastStack } from "../notifications/ToastStack";
import { RemindersPanel } from "../panels/RemindersPanel";
import { ShoppingPanel } from "../panels/ShoppingPanel";
import { MusicPanel } from "../panels/MusicPanel";
import { ThemeToggle } from "../ThemeToggle";
import { speak } from "../../lib/tts";
import { getLocation } from "../../lib/geolocation";
import "./ChatLayout.css";

const HINTS = [
  "What can you do?",
  "What's in front of the camera?",
  "Order me something to eat",
  "Remind me to stretch in an hour",
];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Up late?";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function newId(): string {
  return crypto.randomUUID();
}

function storedOpen(key: string): boolean {
  try {
    return window.localStorage.getItem(key) !== "closed";
  } catch {
    return true;
  }
}

function storeOpen(key: string, open: boolean): void {
  try {
    window.localStorage.setItem(key, open ? "open" : "closed");
  } catch {
    // non-persistent session — fine
  }
}

/** Time travel state: the checkpoint to fork from + the text being edited. */
interface RewindState {
  checkpointId: string | null; // null = restart the thread from scratch
  draft: string;
  /** Index into `messages` of the user message being edited. */
  messageIndex: number;
}

export function ChatView() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { threads, loadThreads, renameThread, deleteThread } = useThreads();
  const {
    activeAgent,
    pendingInterrupt,
    todos,
    setActiveAgent,
    addToolCall,
    addToolResult,
    setPendingInterrupt,
    setTodos,
    resetTurn,
  } = useChatStream();

  const [threadId, setThreadId] = useState<string>(newId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [resolvingInterrupt, setResolvingInterrupt] = useState(false);
  const [alwaysSpeak, setAlwaysSpeak] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [rewind, setRewind] = useState<RewindState | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => storedOpen("ui-threads-rail"));
  const [panelsOpen, setPanelsOpen] = useState(() => storedOpen("ui-panels-rail"));

  const toggleSidebar = () => setSidebarOpen((v) => (storeOpen("ui-threads-rail", !v), !v));
  const togglePanels = () => setPanelsOpen((v) => (storeOpen("ui-panels-rail", !v), !v));

  const chatContainerRef = useRef<HTMLDivElement>(null);
  // "Pinned to bottom" = the user is reading the latest reply, so we follow
  // the stream down. If they scroll up to read history, we stop yanking them.
  // A fast reply used to leave the view parked on the previous answer because
  // the old `scrollTop = scrollHeight` fired before layout settled; anchoring
  // to a sentinel that we scroll into view fixes that.
  const pinnedRef = useRef(true);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  // First-run gate: if the system isn't ready (LLM unreachable, models
  // missing, infra down), land on the setup wizard instead of a broken chat.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch("/system/preflight");
        if (!res.ok) return;
        const data: PreflightResponse = await res.json();
        if (!cancelled && !data.ready) navigate("/setup");
      } catch {
        // Preflight itself failing shouldn't lock the user out of chat.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 4500);
    return () => clearTimeout(t);
  }, [error]);

  // Track whether the user is at the bottom (within 120px). Updated on their
  // manual scrolls; drives whether streaming auto-follows.
  const onScroll = useCallback(() => {
    const el = chatContainerRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  const followBottom = useCallback(() => {
    if (!pinnedRef.current) return;
    // Two rAFs: let the just-rendered markdown/bubble lay out before we
    // measure, so a fast short reply still lands the view on itself.
    requestAnimationFrame(() =>
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ block: "end" })),
    );
  }, []);

  const forceBottom = useCallback(() => {
    pinnedRef.current = true;
    followBottom();
  }, [followBottom]);

  useEffect(followBottom, [messages, followBottom]);

  const startNewThread = useCallback(() => {
    setThreadId(newId());
    setMessages([]);
    setTodos([]);
    setRewind(null);
    pinnedRef.current = true;  // fresh thread starts at the bottom
  }, [setTodos]);

  const selectThread = useCallback(async (id: string) => {
    if (id === threadId) return;
    try {
      const res = await authFetch(`/threads/${id}/messages`);
      if (!res.ok) throw new Error("Could not load that conversation.");
      const data: ThreadMessagesResponse = await res.json();
      setThreadId(id);
      setMessages(
        data.messages.map((m) => ({
          id: newId(),
          role: m.role === "human" ? "user" : "bot",
          content: m.content,
        })),
      );
      setTodos([]);
      setRewind(null);
      pinnedRef.current = true;  // show the loaded conversation's latest message
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [threadId, setTodos]);

  /**
   * Drains a chat/resume SSE generator into the given bot message. Returns
   * false if the turn paused on an interrupt (caller must not clear the
   * "sending" lock in that case — resumeTurn owns it from here).
   */
  const consumeIntoMessage = useCallback(async (
    generator: AsyncGenerator<ChatEvent>,
    botId: string,
    initialText: string,
  ): Promise<boolean> => {
    let fullText = initialText;
    for await (const event of generator) {
      if ("error" in event) {
        throw new Error(event.error);
      }
      if ("done" in event) {
        if (event.thread_id && event.thread_id !== threadId) {
          setThreadId(event.thread_id);
        }
        // Always clear the thinking state on completion — a turn that ended
        // with no text delta (pure tool/handoff) would otherwise hang on
        // "Thinking" forever.
        setMessages((prev) =>
          prev.map((m) => (m.id === botId && m.thinking
            ? { ...m, thinking: false, content: m.content || "Done." }
            : m)),
        );
        // Voice mode: the browser speaks the finished reply (speechSynthesis).
        if (alwaysSpeak && fullText) speak(fullText);
        continue;
      }
      if ("agent" in event) {
        setActiveAgent(event.agent);
        continue;
      }
      if ("progress" in event) {
        // Long-tool progress: shown in the thinking bubble while it lasts.
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, progressText: event.progress } : m)),
        );
        continue;
      }
      if ("tool_call" in event) {
        addToolCall(event.tool_call);
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, toolActivity: useChatStream.getState().toolTimeline } : m)),
        );
        if (event.tool_call.name === "write_todos") {
          const args = event.tool_call.args as { todos?: Todo[] } | undefined;
          if (args?.todos) setTodos(args.todos);
        }
        continue;
      }
      if ("tool_result" in event) {
        addToolResult(event.tool_result);
        setMessages((prev) =>
          prev.map((m) => (m.id === botId
            ? { ...m, toolActivity: useChatStream.getState().toolTimeline, progressText: undefined }
            : m)),
        );
        continue;
      }
      if ("interrupt" in event) {
        setPendingInterrupt({ ...event.interrupt, botId });
        return false;
      }
      if ("delta" in event && event.delta) {
        fullText += event.delta;
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, content: fullText, thinking: false } : m)),
        );
      }
    }
    return true;
  }, [threadId, alwaysSpeak, setActiveAgent, addToolCall, addToolResult, setPendingInterrupt, setTodos]);

  const sendMessage = useCallback(async (query: string) => {
    setSending(true);
    resetTurn();

    // Time travel: forking truncates the visible transcript to the shared
    // prefix before appending the edited message. Editing the FIRST message
    // has no earlier checkpoint — it becomes a fresh thread instead.
    const activeRewind = rewind;
    setRewind(null);
    let tid = threadId;
    if (activeRewind) {
      if (activeRewind.checkpointId === null) {
        tid = newId();
        setThreadId(tid);
        setMessages([]);
      } else {
        setMessages((prev) => prev.slice(0, activeRewind.messageIndex));
      }
    }

    setMessages((prev) => [...prev, { id: newId(), role: "user", content: query }]);
    const botId = newId();
    setMessages((prev) => [...prev, { id: botId, role: "bot", content: "", thinking: true }]);
    // Sending my own message always snaps the view to the bottom.
    forceBottom();

    try {
      // Location is best-effort: null on deny/timeout, cached 5 min.
      const location = await getLocation();
      const finished = await consumeIntoMessage(
        streamChat(tid, query, alwaysSpeak, location, activeRewind?.checkpointId ?? null),
        botId,
        "",
      );
      if (finished) {
        loadThreads();
        setSending(false);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setMessages((prev) =>
        prev.map((m) => (m.id === botId ? { ...m, content: `Error: ${message}`, thinking: false } : m)),
      );
      setError(message);
      setSending(false);
    }
  }, [threadId, alwaysSpeak, loadThreads, resetTurn, consumeIntoMessage, rewind, forceBottom]);

  /** "Edit & resend from here": find the turn-boundary checkpoint BEFORE the
   * k-th user message and stage a fork. Boundaries come back newest-first,
   * one per completed turn — reversed, boundary[k-2] precedes user turn k. */
  const startRewind = useCallback(async (messageIndex: number) => {
    const target = messages[messageIndex];
    if (!target || target.role !== "user" || sending) return;
    const userTurnNumber = messages
      .slice(0, messageIndex + 1)
      .filter((m) => m.role === "user").length;
    try {
      if (userTurnNumber === 1) {
        // Nothing before the first message — sending will restart the thread.
        setRewind({ checkpointId: null, draft: target.content, messageIndex });
        return;
      }
      const res = await authFetch(`/threads/${threadId}/checkpoints`);
      if (!res.ok) throw new Error("Could not load this conversation's history.");
      const data: { checkpoints: ThreadCheckpoint[] } = await res.json();
      const boundaries = [...data.checkpoints].reverse(); // oldest first
      const before = boundaries[userTurnNumber - 2];
      if (!before) throw new Error("No rewind point found for that message.");
      setRewind({ checkpointId: before.checkpoint_id, draft: target.content, messageIndex });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [messages, sending, threadId]);

  const resumeTurn = useCallback(async (decisions: ResumeDecision[]) => {
    if (!pendingInterrupt) return;
    const { botId } = pendingInterrupt;
    setResolvingInterrupt(true);
    setPendingInterrupt(null);
    const currentText = messages.find((m) => m.id === botId)?.content ?? "";

    try {
      const finished = await consumeIntoMessage(
        resumeChat(threadId, decisions, alwaysSpeak),
        botId,
        currentText,
      );
      if (finished) {
        loadThreads();
        setSending(false);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setMessages((prev) =>
        prev.map((m) => (m.id === botId ? { ...m, content: `Error: ${message}`, thinking: false } : m)),
      );
      setError(message);
      setSending(false);
    } finally {
      setResolvingInterrupt(false);
    }
  }, [pendingInterrupt, messages, threadId, alwaysSpeak, loadThreads, consumeIntoMessage, setPendingInterrupt]);

  return (
    <div className="app-shell">
      <div className="aurora" aria-hidden />
      <EventsBridge />
      <ToastStack />
      <div className="header">
        <div className="header-left">
          <button
            className={`rail-toggle${sidebarOpen ? " on" : ""}`}
            onClick={toggleSidebar}
            title={sidebarOpen ? "Hide conversations" : "Show conversations"}
            aria-label="Toggle conversations sidebar"
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="3" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
          </button>
          <button
            className={`rail-toggle${panelsOpen ? " on" : ""}`}
            onClick={togglePanels}
            title={panelsOpen ? "Hide panels" : "Show panels (camera, reminders, shopping, music)"}
            aria-label="Toggle panels rail"
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" />
            </svg>
          </button>
          <div className="logo-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h1>Sub<span className="wordmark-accent">Agents</span></h1>
        </div>
        <AgentDock activeAgent={activeAgent} />
        <div className="header-right">
          <div className="header-pill">
            <span style={{ fontSize: 10 }}>VOICE</span>
            <button className="btn-tiny" onClick={() => setAlwaysSpeak((v) => !v)} type="button">
              {alwaysSpeak ? "ON" : "OFF"}
            </button>
          </div>
          <ThreadIdChip threadId={threadId} />
          <WakeWordIndicator />
          <VoiceWaveform />
          <ThemeToggle />
          <div className="user-menu">
            <button className="user-avatar-btn" onClick={() => setMenuOpen((v) => !v)} type="button">
              <span className="avatar-circle">{user?.email?.[0]?.toUpperCase() ?? "?"}</span>
              <span className="user-email">{user?.email ?? "…"}</span>
            </button>
            <div className={`user-dropdown${menuOpen ? " open" : ""}`}>
              <div className="user-dropdown-email">{user?.email}</div>
              <div className="user-dropdown-item" onClick={() => navigate("/settings")}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>
                Settings
              </div>
              <div className="user-dropdown-item" onClick={() => navigate("/setup")}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                System check
              </div>
              <div className="user-dropdown-item" onClick={() => navigate("/account")}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                Account
              </div>
              <div className="user-dropdown-item danger" onClick={logout}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg>
                Log out
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="main-content">
        <ThreadSidebar
          threads={threads}
          activeThreadId={threadId}
          open={sidebarOpen}
          onSelect={selectThread}
          onDelete={(id) => { deleteThread(id); if (id === threadId) startNewThread(); }}
          onRename={renameThread}
          onNewThread={startNewThread}
        />

        {/* Kept mounted when closed (CSS collapse) so the camera stream and
            panel state survive hiding the rail. */}
        <div className={`left-panel${panelsOpen ? "" : " closed"}`}>
          <div className="section-label">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
            Panels
          </div>
          {todos && todos.length > 0 && <PlanCard todos={todos} />}
          <CameraPanel threadId={threadId} />
          <RemindersPanel />
          <ShoppingPanel />
          <MusicPanel />
        </div>

        <div className="right-panel">
          <div className="chat-container" ref={chatContainerRef} onScroll={onScroll}>
            {messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.5 1.5M16.9 16.9l1.5 1.5M5.6 18.4l1.5-1.5M16.9 7.1l1.5-1.5" />
                    <circle cx="12" cy="12" r="4" />
                  </svg>
                </div>
                <h2>{greeting()}.</h2>
                <p>Six agents, your camera, your voice — all on your own hardware.<br />Ask anything, or try one of these:</p>
                <div className="welcome-hints">
                  {HINTS.map((hint) => (
                    <button key={hint} className="hint-chip" onClick={() => sendMessage(hint)} type="button">
                      {hint}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <MessageBubble
                  key={m.id}
                  {...m}
                  onRewind={m.role === "user" && !sending ? () => startRewind(i) : undefined}
                />
              ))
            )}
            {pendingInterrupt && (
              <InterruptCard
                actionRequests={pendingInterrupt.action_requests}
                onResolve={resumeTurn}
                resolving={resolvingInterrupt}
              />
            )}
            {/* Scroll anchor: the view follows this into view while pinned. */}
            <div ref={endRef} aria-hidden style={{ height: 1 }} />
          </div>
          <Composer
            onSend={sendMessage}
            sending={sending}
            alwaysSpeak={alwaysSpeak}
            onToggleAlwaysSpeak={() => setAlwaysSpeak((v) => !v)}
            rewindDraft={rewind?.draft ?? null}
            onCancelRewind={() => setRewind(null)}
          />
        </div>
      </div>

      {error && <div className="error-toast">{error}</div>}
    </div>
  );
}
