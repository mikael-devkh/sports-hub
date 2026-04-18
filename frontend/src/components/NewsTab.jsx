import { useEffect, useState } from "react";
import { api } from "../api/client";

const DEFAULT_TEAMS = [
  { key: "sao-paulo", label: "São Paulo" },
  { key: "celtics",   label: "Boston Celtics" },
  { key: "santos",      label: "Santos" },
  { key: "corinthians", label: "Corinthians" },
  { key: "palmeiras",   label: "Palmeiras" },
  { key: "flamengo",    label: "Flamengo" },
];

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export default function NewsTab() {
  const [teamKey, setTeamKey] = useState("sao-paulo");
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.teamNews(teamKey, 25)
      .then((d) => { if (!cancelled) setItems(d.items || []); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [teamKey]);

  return (
    <div className="news">
      <div className="news__filter">
        {DEFAULT_TEAMS.map((t) => (
          <button
            key={t.key}
            className={teamKey === t.key ? "pill pill--active" : "pill"}
            onClick={() => setTeamKey(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <p className="dashboard__loading">Carregando notícias…</p>}
      {error   && <p className="dashboard__error">Erro: {error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="dashboard__empty">Nenhuma notícia encontrada.</p>
      )}

      <ul className="news__list">
        {items.map((n, i) => (
          <li key={i} className="news__item">
            <a href={n.link} target="_blank" rel="noopener noreferrer" className="news__link">
              <span className="news__title">{n.title}</span>
              <span className="news__meta">
                {n.source && <span className="news__source">{n.source}</span>}
                {n.published && <span className="news__date">{formatDate(n.published)}</span>}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
