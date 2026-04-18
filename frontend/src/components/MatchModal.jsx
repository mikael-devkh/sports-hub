import { useEffect, useState } from "react";
import { api } from "../api/client";

function formatFull(iso) {
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    weekday: "long", day: "2-digit", month: "long",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function MatchModal({ matchId, onClose }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  useEffect(() => {
    if (!matchId) return;
    let cancelled = false;
    setLoading(true);
    api.matchDetail(matchId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [matchId]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!matchId) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose} aria-label="Fechar">×</button>

        {loading && <p>Carregando…</p>}
        {error   && <p className="dashboard__error">Erro: {error}</p>}
        {data && (
          <>
            <div className="modal__header">
              <span className="modal__league">
                {data.league.logo && <img src={data.league.logo} alt="" />}
                {data.league.name}
              </span>
              <span className="modal__status">{data.status_label}</span>
            </div>

            <div className="modal__teams">
              <div className="modal__team">
                {data.home_team.logo && <img src={data.home_team.logo} alt={data.home_team.name} />}
                <strong>{data.home_team.name}</strong>
              </div>
              <div className="modal__score">
                {data.status === "NS"
                  ? "vs"
                  : `${data.score.home ?? 0} — ${data.score.away ?? 0}`}
              </div>
              <div className="modal__team">
                {data.away_team.logo && <img src={data.away_team.logo} alt={data.away_team.name} />}
                <strong>{data.away_team.name}</strong>
              </div>
            </div>

            <div className="modal__info">
              <div className="modal__row">
                <span className="modal__label">🕐 Quando</span>
                <span>{formatFull(data.scheduled_at)}</span>
              </div>
              {data.venue && (
                <div className="modal__row">
                  <span className="modal__label">📍 Onde</span>
                  <span>{data.venue}</span>
                </div>
              )}
              <div className="modal__row">
                <span className="modal__label">📺 Transmissão</span>
                <span>
                  {data.broadcast.length > 0
                    ? data.broadcast.join(" · ")
                    : "Não disponível"}
                </span>
              </div>
            </div>

            {(data.lineups?.home?.length > 0 || data.lineups?.away?.length > 0) && (
              <div className="modal__lineups">
                <h4>Escalação</h4>
                <div className="modal__lineups-grid">
                  <ul>
                    {data.lineups.home.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                  <ul>
                    {data.lineups.away.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
