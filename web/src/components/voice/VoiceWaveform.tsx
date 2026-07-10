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
          // Rounded bars mirrored around the vertical center, tinted with
          // the signature cyan→violet spectrum.
          const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
          gradient.addColorStop(0, "#22d3ee");
          gradient.addColorStop(0.55, "#818cf8");
          gradient.addColorStop(1, "#c084fc");
          ctx.fillStyle = gradient;
          const barWidth = canvas.width / data.length;
          const mid = canvas.height / 2;
          for (let i = 0; i < data.length; i++) {
            const barHeight = Math.max((data[i] / 255) * canvas.height, 2);
            const w = Math.max(barWidth - 2, 1.5);
            const x = i * barWidth;
            ctx.beginPath();
            ctx.roundRect(x, mid - barHeight / 2, w, barHeight, w / 2);
            ctx.fill();
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
