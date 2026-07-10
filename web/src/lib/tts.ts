/** Browser text-to-speech via the Web Speech API.
 *
 * Chrome silently cuts off utterances longer than ~15s, so text is split into
 * sentence-sized chunks queued as separate utterances. Markdown syntax is
 * stripped first — the assistant streams markdown, and reading "asterisk
 * asterisk" aloud is useless.
 */

const supported = typeof window !== "undefined" && "speechSynthesis" in window;

function stripMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " code block omitted. ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/(\*\*|__|\*|_|~~)/g, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/\|/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Split into chunks of whole sentences, each short enough to survive Chrome. */
function chunkSentences(text: string, maxLen = 200): string[] {
  const sentences = text.match(/[^.!?]+[.!?]+["']?|[^.!?]+$/g) ?? [text];
  const chunks: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    if (current && current.length + sentence.length > maxLen) {
      chunks.push(current.trim());
      current = "";
    }
    current += sentence;
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

// Chrome silently pauses the synthesis engine after ~15s of speaking and never
// resumes on its own; a periodic resume() keepalive defeats that. We also chain
// chunks one utterance at a time via onend (Chrome stalls a multi-utterance
// queue) and cancel()+resume() before each reply to unstick an engine that a
// previous turn left in a stuck "paused" state — the usual cause of the
// intermittent "no voice at all" symptom.
let keepAlive: ReturnType<typeof setInterval> | null = null;

function clearKeepAlive(): void {
  if (keepAlive) {
    clearInterval(keepAlive);
    keepAlive = null;
  }
}

export function speak(text: string): void {
  if (!supported) return;
  const clean = stripMarkdown(text);
  if (!clean) return;

  const synth = window.speechSynthesis;
  clearKeepAlive();
  synth.cancel();
  // A prior long reply can leave the engine paused; cancel() alone doesn't
  // always clear that, so kick it back to life before we queue anything.
  synth.resume();

  const chunks = chunkSentences(clean);
  let i = 0;

  const speakNext = (): void => {
    if (i >= chunks.length) {
      clearKeepAlive();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(chunks[i++]);
    utterance.rate = 1.0;
    utterance.onend = speakNext;
    utterance.onerror = speakNext; // never stall the queue on a single failure
    synth.speak(utterance);
  };

  // Keepalive: nudge Chrome every 10s so it doesn't auto-pause mid-reply.
  keepAlive = setInterval(() => {
    if (synth.speaking) synth.resume();
    else clearKeepAlive();
  }, 10000);

  speakNext();
}

export function stopSpeaking(): void {
  if (!supported) return;
  clearKeepAlive();
  window.speechSynthesis.cancel();
}
