import { useMemo } from "react";

const STATUS_LABEL = {
  NS:   null,
  FT:   "Encerrado",
  "1H": "1º Tempo",
  HT:   "Intervalo",
  "2H": "2º Tempo",
  AET:  "Prorrogação",
  PEN:  "Pênaltis",
  CANC: "Cancelado",
  PST:  "Adiado",
};

const SPORT_ICON = { football: "⚽", basketball: "🏀" };

function formatDateTime(iso) {
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" }),
    time: d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
  };
}

export default function MatchCard({ match, onClick }) {
  const { date, time } = useMemo(() => formatDateTime(match.scheduled_at), [match.scheduled_at]);
  const isLive    = ["1H", "HT", "2H", "AET", "PEN"].includes(match.status);
  const isFinished = match.status === "FT";
  const statusLabel = STATUS_LABEL[match.status];

  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      className={[
        "match-card",
        onClick && "match-card--clickable",
        isLive     && "match-card--live",
        isFinished && "match-card--finished",
        match.home_team.tracked || match.away_team.tracked ? "match-card--tracked" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {/* Header: liga + data */}
      <div className="match-card__header">
        <span className="match-card__sport">{SPORT_ICON[match.sport]}</span>
        {match.league.logo && (
          <img src={match.league.logo} alt={match.league.name} className="match-card__league-logo" />
        )}
        <span className="match-card__league">{match.league.name}</span>
        <span className="match-card__date">{date}</span>
      </div>

      {/* Placar / times */}
      <div className="match-card__body">
        <Team team={match.home_team} />

        <div className="match-card__center">
          {isFinished || isLive ? (
            <span className="match-card__score">
              {match.score.home ?? 0} — {match.score.away ?? 0}
            </span>
          ) : (
            <span className="match-card__time">{time}</span>
          )}
          {statusLabel && (
            <span className={`match-card__status ${isLive ? "match-card__status--live" : ""}`}>
              {isLive && <span className="live-dot" />}
              {statusLabel}
            </span>
          )}
        </div>

        <Team team={match.away_team} />
      </div>

      {/* Canais de TV */}
      <div className="match-card__broadcast">
        <span className="match-card__broadcast-icon">📺</span>
        {match.broadcast.length > 0
          ? match.broadcast.join(" · ")
          : <span style={{color:"var(--muted)"}}>Transmissão não disponível</span>
        }
      </div>

      {match.venue && (
        <div className="match-card__venue">📍 {match.venue}</div>
      )}
    </div>
  );
}

function Team({ team }) {
  return (
    <div className="match-card__team">
      {team.logo ? (
        <img src={team.logo} alt={team.name} className="match-card__team-logo" />
      ) : (
        <div className="match-card__team-logo match-card__team-logo--placeholder" />
      )}
      <span className={`match-card__team-name ${team.tracked ? "match-card__team-name--tracked" : ""}`}>
        {team.name}
      </span>
    </div>
  );
}
