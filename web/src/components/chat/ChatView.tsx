import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "../../api/client";
import { resumeChat, streamChat } from "../../api/stream";
import type { ChatEvent, ResumeDecision, ThreadMessagesResponse, Todo } from "../../api/types";
import { useAuth } from "../../state/AuthContext";
import { useChatStream } from "../../state/chatStream";
import { useThreads } from "../../hooks/useThreads";
import { ThreadSidebar } from "../sidebar/ThreadSidebar";
import { MessageBubble, type ChatMessage } from "./MessageBubble";
import { AgentBadge } from "./AgentBadge";
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
import { speak } from "../../lib/tts";
import { getLocation } from "../../lib/geolocation";
import "./ChatView.css";

const HINTS = ["What can you do?", "Help me with a task", "Tell me about yourself"];

function newId(): string {
  return crypto.randomUUID();
}

export function ChatView() {
  const { user, logout } = useAuth();
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

  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 4500);
    return () => clearTimeout(t);
  }, [error]);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = chatContainerRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(scrollToBottom, [messages, scrollToBottom]);

  const startNewThread = useCallback(() => {
    setThreadId(newId());
    setMessages([]);
    setTodos([]);
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
        // Voice mode: the browser speaks the finished reply (speechSynthesis).
        if (alwaysSpeak && fullText) speak(fullText);
        continue;
      }
      if ("agent" in event) {
        setActiveAgent(event.agent);
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
          prev.map((m) => (m.id === botId ? { ...m, toolActivity: useChatStream.getState().toolTimeline } : m)),
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
    setMessages((prev) => [...prev, { id: newId(), role: "user", content: query }]);
    const botId = newId();
    setMessages((prev) => [...prev, { id: botId, role: "bot", content: "", thinking: true }]);

    try {
      // Location is best-effort: null on deny/timeout, cached 5 min.
      const location = await getLocation();
      const finished = await consumeIntoMessage(streamChat(threadId, query, alwaysSpeak, location), botId, "");
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
  }, [threadId, alwaysSpeak, loadThreads, resetTurn, consumeIntoMessage]);

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
      <EventsBridge />
      <ToastStack />
      <div className="header">
        <div className="header-left">
          <div className="logo-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h1>SubAgents</h1>
        </div>
        <div className="header-right">
          <div className="header-pill">
            <span style={{ fontSize: 10 }}>VOICE:</span>
            <button className="btn-tiny" onClick={() => setAlwaysSpeak((v) => !v)} type="button">
              {alwaysSpeak ? "ON" : "OFF"}
            </button>
          </div>
          <AgentBadge agent={activeAgent} />
          <WakeWordIndicator />
          <VoiceWaveform />
          <span className="header-pill" title={threadId}>{threadId.slice(0, 8)}...</span>
          <div className="user-menu">
            <button className="user-avatar-btn" onClick={() => setMenuOpen((v) => !v)} type="button">
              <span className="avatar-circle">{user?.email?.[0]?.toUpperCase() ?? "?"}</span>
              <span className="user-email">{user?.email ?? "…"}</span>
            </button>
            <div className={`user-dropdown${menuOpen ? " open" : ""}`}>
              <div className="user-dropdown-email">{user?.email}</div>
              <div className="user-dropdown-item" onClick={() => (window.location.href = "/account")}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>
                Account settings
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
          onSelect={selectThread}
          onDelete={(id) => { deleteThread(id); if (id === threadId) startNewThread(); }}
          onRename={renameThread}
          onNewThread={startNewThread}
        />

        <div className="left-panel">
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
          <div className="chat-container" ref={chatContainerRef}>
            {messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                  </svg>
                </div>
                <h2>SubAgents</h2>
                <p>Your multi-agent AI assistant.<br />Try one of these to get started:</p>
                <div className="welcome-hints">
                  {HINTS.map((hint) => (
                    <button key={hint} className="hint-chip" onClick={() => sendMessage(hint)} type="button">
                      {hint}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} {...m} />)
            )}
            {pendingInterrupt && (
              <InterruptCard
                actionRequests={pendingInterrupt.action_requests}
                onResolve={resumeTurn}
                resolving={resolvingInterrupt}
              />
            )}
          </div>
          <Composer
            onSend={sendMessage}
            sending={sending}
            alwaysSpeak={alwaysSpeak}
            onToggleAlwaysSpeak={() => setAlwaysSpeak((v) => !v)}
          />
        </div>
      </div>

      {error && <div className="error-toast">{error}</div>}
    </div>
  );
}
