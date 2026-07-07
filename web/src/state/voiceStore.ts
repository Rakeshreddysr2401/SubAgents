import { create } from "zustand";

interface VoiceState {
  listening: boolean;
  wakeSignal: number;
  setListening: (listening: boolean) => void;
  triggerWake: () => void;
}

/** Shared between Composer (owns SpeechRecognition), WakeWordIndicator (owns
 * the /events subscription that can trigger listening remotely), and
 * VoiceWaveform (purely visual, reacts to `listening`). */
export const useVoiceStore = create<VoiceState>((set) => ({
  listening: false,
  wakeSignal: 0,
  setListening: (listening) => set({ listening }),
  triggerWake: () => set((s) => ({ wakeSignal: s.wakeSignal + 1 })),
}));
