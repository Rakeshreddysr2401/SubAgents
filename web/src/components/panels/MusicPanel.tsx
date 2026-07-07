import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "../../api/client";
import { useMusicStore } from "../../state/musicStore";
import "./Panels.css";

interface Station {
  name: string;
  url: string;
}

export function MusicPanel() {
  const nowPlaying = useMusicStore((s) => s.nowPlaying);
  const play = useMusicStore((s) => s.play);
  const stop = useMusicStore((s) => s.stop);
  const [stations, setStations] = useState<Station[]>([]);
  const [selected, setSelected] = useState(0);
  const [needsGesture, setNeedsGesture] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    authFetch("/music/stations")
      .then((res) => (res.ok ? res.json() : { stations: [] }))
      .then((data) => setStations(data.stations ?? []))
      .catch(() => {});
  }, []);

  // The store is the source of truth (tool events land there via EventsBridge);
  // this effect syncs the actual <audio> element to it.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!nowPlaying) {
      audio.pause();
      audio.removeAttribute("src");
      setNeedsGesture(false);
      return;
    }
    audio.src = nowPlaying.url;
    audio.play().then(
      () => setNeedsGesture(false),
      // Autoplay blocked (no user gesture, e.g. tool-triggered play): show a
      // tap-to-play button instead of failing silently.
      () => setNeedsGesture(true),
    );
  }, [nowPlaying]);

  const tapToPlay = useCallback(() => {
    audioRef.current?.play().then(() => setNeedsGesture(false), () => {});
  }, []);

  const playSelected = useCallback(() => {
    const station = stations[selected];
    if (station) play({ url: station.url, station: station.name });
  }, [stations, selected, play]);

  return (
    <div className="tools-card panel-card">
      <div className="tools-card-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 18V5l12-2v13" />
          <circle cx="6" cy="18" r="3" />
          <circle cx="18" cy="16" r="3" />
        </svg>
        Music
      </div>
      <div className="panel-body">
        <audio ref={audioRef} />
        {nowPlaying ? (
          <>
            <div className="music-now-playing">
              <span className="music-eq"><span /><span /><span /></span>
              {nowPlaying.station}
            </div>
            <div className="music-controls">
              {needsGesture && (
                <button className="music-btn playing" onClick={tapToPlay} type="button">
                  ▶ Tap to play
                </button>
              )}
              <button className="music-btn" onClick={stop} type="button">
                ■ Stop
              </button>
            </div>
          </>
        ) : (
          <div className="music-controls">
            <select
              className="music-select"
              value={selected}
              onChange={(e) => setSelected(Number(e.target.value))}
            >
              {stations.map((s, i) => (
                <option key={s.url} value={i}>{s.name}</option>
              ))}
            </select>
            <button className="music-btn" onClick={playSelected} disabled={stations.length === 0} type="button">
              ▶ Play
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
