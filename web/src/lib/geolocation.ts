/** Browser geolocation with a short cache — sent along with each chat turn.
 *
 * Never blocks sending: resolves null on deny/timeout/unsupported. The fix is
 * cached for 5 minutes so we don't spin up the GPS on every message.
 */

export interface Location {
  lat: number;
  lon: number;
  accuracy_m: number | null;
}

const CACHE_MS = 5 * 60 * 1000;
const FIX_TIMEOUT_MS = 3000;

let cached: { location: Location; at: number } | null = null;
let denied = false;

export function getLocation(): Promise<Location | null> {
  if (denied || !("geolocation" in navigator)) return Promise.resolve(null);
  if (cached && Date.now() - cached.at < CACHE_MS) return Promise.resolve(cached.location);

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const location: Location = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy ?? null,
        };
        cached = { location, at: Date.now() };
        resolve(location);
      },
      (err) => {
        // PERMISSION_DENIED is sticky for the session — don't re-prompt.
        if (err.code === err.PERMISSION_DENIED) denied = true;
        resolve(null);
      },
      { maximumAge: CACHE_MS, timeout: FIX_TIMEOUT_MS },
    );
  });
}
