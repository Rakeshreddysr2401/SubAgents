import { useEffect, useRef } from "react";
import { useVoiceStore } from "../../state/voiceStore";

/** Purely visual mic-level waveform, active only while Composer is listening. */
export function VoiceWaveform() {
  const listening = useVoiceStore((s) => s.listening);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!listening) return;
    let stream: MediaStream | null = null;
    let audioCtx: AudioContext | null = null;
    let source: MediaStreamAudioSourceNode | null = null;
    let cancelled = false;

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        audioCtx = new AudioContext();
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;
        source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext("2d");

        const draw = () => {
          if (!ctx || !canvas) return;
          analyser.getByteFrequencyData(data);
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          const barWidth = canvas.width / data.length;
          for (let i = 0; i < data.length; i++) {
            const barHeight = (data[i] / 255) * canvas.height;
            ctx.fillStyle = "#6366f1";
            ctx.fillRect(i * barWidth, canvas.height - barHeight, Math.max(barWidth - 1, 1), barHeight);
          }
          rafRef.current = requestAnimationFrame(draw);
        };
        draw();
      } catch {
        // mic denied/unavailable — Composer's own mic button already surfaces this
      }
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
      source?.disconnect();
      audioCtx?.close();
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [listening]);

  if (!listening) return null;
  return <canvas ref={canvasRef} className="voice-waveform" width={120} height={32} />;
}
