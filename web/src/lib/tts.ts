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

export function speak(text: string): void {
  if (!supported) return;
  const clean = stripMarkdown(text);
  if (!clean) return;
  window.speechSynthesis.cancel();
  for (const chunk of chunkSentences(clean)) {
    const utterance = new SpeechSynthesisUtterance(chunk);
    utterance.rate = 1.0;
    window.speechSynthesis.speak(utterance);
  }
}

export function stopSpeaking(): void {
  if (supported) window.speechSynthesis.cancel();
}
