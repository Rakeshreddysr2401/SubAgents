import { create } from "zustand";

export interface NowPlaying {
  url: string;
  station: string;
}

interface MusicState {
  nowPlaying: NowPlaying | null;
  play: (nowPlaying: NowPlaying) => void;
  stop: () => void;
}

/** Written by EventsBridge (play_music/stop_music tool events) and MusicPanel
 * (manual station picks); MusicPanel owns the actual <audio> element. */
export const useMusicStore = create<MusicState>((set) => ({
  nowPlaying: null,
  play: (nowPlaying) => set({ nowPlaying }),
  stop: () => set({ nowPlaying: null }),
}));
