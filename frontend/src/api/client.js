const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

async function get(path, params = {}) {
  const url = new URL(`${BASE}${path}`);
  Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  upcomingMatches: (days = 7, sport = null) =>
    get("/matches/upcoming", { days, sport }),
  liveMatches: () =>
    get("/matches/live"),
  recentMatches: (days = 3) =>
    get("/matches/recent", { days }),
  standings: (leagueApiId, season = 2025) =>
    get(`/standings/${leagueApiId}`, { season }),
};
