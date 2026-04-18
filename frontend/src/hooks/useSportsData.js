import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

export function useUpcomingMatches(days = 7, sport = null) {
  const [data, setData]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.upcomingMatches(days, sport));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [days, sport]);

  useEffect(() => { fetch_(); }, [fetch_]);
  return { data, loading, error, refetch: fetch_ };
}

export function useStandings(leagueApiId, season = 2025) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.standings(leagueApiId, season)
      .then(d => { if (!cancelled) setData(d); })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueApiId, season]);

  return { data, loading, error };
}
