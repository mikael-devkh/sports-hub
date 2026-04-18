import { useStandings } from "../hooks/useSportsData";

const FORM_COLOR = { W: "#22c55e", D: "#facc15", L: "#ef4444" };

function FormBadge({ char }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 18,
        height: 18,
        borderRadius: "50%",
        background: FORM_COLOR[char] ?? "#6b7280",
        color: "#fff",
        fontSize: 10,
        fontWeight: 700,
        lineHeight: "18px",
        textAlign: "center",
        marginRight: 2,
      }}
    >
      {char}
    </span>
  );
}

export default function StandingsTable({ leagueApiId, leagueName, season = 2025 }) {
  const { data, loading, error } = useStandings(leagueApiId, season);

  if (loading) return <p className="standings__loading">Carregando {leagueName}…</p>;
  if (error)   return <p className="standings__error">Erro: {error}</p>;
  if (!data?.table?.length) return null;

  return (
    <div className="standings">
      <h3 className="standings__title">{data.league}</h3>
      <table className="standings__table">
        <thead>
          <tr>
            <th>#</th>
            <th>Time</th>
            <th title="Jogos">J</th>
            <th title="Vitórias">V</th>
            <th title="Empates">E</th>
            <th title="Derrotas">D</th>
            <th title="Saldo de gols">SG</th>
            <th title="Pontos">Pts</th>
            <th>Forma</th>
          </tr>
        </thead>
        <tbody>
          {data.table.map((row) => (
            <tr
              key={row.team.name}
              className={row.team.tracked ? "standings__row--tracked" : ""}
            >
              <td>{row.position}</td>
              <td className="standings__team">
                {row.team.logo && (
                  <img src={row.team.logo} alt={row.team.name} className="standings__team-logo" />
                )}
                <span>{row.team.name}</span>
              </td>
              <td>{row.played}</td>
              <td>{row.won}</td>
              <td>{row.drawn}</td>
              <td>{row.lost}</td>
              <td>{row.goal_diff > 0 ? `+${row.goal_diff}` : row.goal_diff}</td>
              <td><strong>{row.points}</strong></td>
              <td>
                {(row.form ?? "").split("").map((c, i) => (
                  <FormBadge key={i} char={c} />
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
