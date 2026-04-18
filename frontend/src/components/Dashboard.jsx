import { useState } from "react";
import { useUpcomingMatches } from "../hooks/useSportsData";
import MatchCard from "./MatchCard";
import StandingsTable from "./StandingsTable";

const LEAGUES = [
  { api_id: 71,  name: "Brasileirão" },
  { api_id: 73,  name: "Copa do Brasil" },
  { api_id: 13,  name: "Libertadores" },
  { api_id: 11,  name: "Sul-Americana" },
  { api_id: 2,   name: "Champions League" },
  { api_id: 3,   name: "Europa League" },
];

const SPORT_TABS = [
  { value: null,         label: "Todos" },
  { value: "football",   label: "⚽ Futebol" },
  { value: "basketball", label: "🏀 Basquete" },
];

function groupByDate(matches) {
  return matches.reduce((acc, m) => {
    const day = new Date(m.scheduled_at).toLocaleDateString("pt-BR", {
      weekday: "long", day: "2-digit", month: "long",
    });
    (acc[day] ??= []).push(m);
    return acc;
  }, {});
}

export default function Dashboard() {
  const [sport, setSport]         = useState(null);
  const [activeTab, setActiveTab] = useState("matches");
  const { data, loading, error, refetch } = useUpcomingMatches(7, sport);

  const grouped = groupByDate(data);

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1 className="dashboard__title">Sports Hub</h1>
        <button onClick={refetch} className="btn-refresh" title="Atualizar">↻</button>
      </header>

      {/* Tabs principais */}
      <nav className="dashboard__tabs">
        <button
          className={activeTab === "matches" ? "tab tab--active" : "tab"}
          onClick={() => setActiveTab("matches")}
        >
          Jogos
        </button>
        <button
          className={activeTab === "standings" ? "tab tab--active" : "tab"}
          onClick={() => setActiveTab("standings")}
        >
          Classificações
        </button>
      </nav>

      {activeTab === "matches" && (
        <>
          {/* Filtro de esporte */}
          <div className="dashboard__sport-filter">
            {SPORT_TABS.map((t) => (
              <button
                key={String(t.value)}
                className={sport === t.value ? "pill pill--active" : "pill"}
                onClick={() => setSport(t.value)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {loading && <p className="dashboard__loading">Buscando jogos…</p>}
          {error   && <p className="dashboard__error">Erro ao carregar: {error}</p>}

          {!loading && !error && data.length === 0 && (
            <p className="dashboard__empty">Nenhum jogo nos próximos 7 dias.</p>
          )}

          {Object.entries(grouped).map(([day, matches]) => (
            <section key={day} className="match-group">
              <h2 className="match-group__date">{day}</h2>
              <div className="match-group__grid">
                {matches.map((m) => (
                  <MatchCard key={m.id} match={m} />
                ))}
              </div>
            </section>
          ))}
        </>
      )}

      {activeTab === "standings" && (
        <div className="standings-grid">
          {LEAGUES.map((l) => (
            <StandingsTable key={l.api_id} leagueApiId={l.api_id} leagueName={l.name} />
          ))}
        </div>
      )}
    </div>
  );
}
