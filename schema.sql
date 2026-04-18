-- ============================================================
-- Sports Hub — DDL Schema (PostgreSQL)
-- ============================================================

CREATE TABLE IF NOT EXISTS leagues (
    id         SERIAL PRIMARY KEY,
    name       TEXT    NOT NULL,
    sport      TEXT    NOT NULL CHECK (sport IN ('football', 'basketball')),
    country    TEXT,
    api_id     BIGINT UNIQUE,
    season     INTEGER NOT NULL,
    logo_url   TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS teams (
    id         SERIAL PRIMARY KEY,
    name       TEXT    NOT NULL,
    short_name TEXT,
    sport      TEXT    NOT NULL CHECK (sport IN ('football', 'basketball')),
    api_id     BIGINT UNIQUE,
    logo_url   TEXT,
    country    TEXT,
    tracked    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS matches (
    id              SERIAL PRIMARY KEY,
    api_id          INTEGER UNIQUE,
    sport           TEXT    NOT NULL CHECK (sport IN ('football', 'basketball')),
    league_id       INTEGER NOT NULL REFERENCES leagues(id),
    home_team_id    INTEGER NOT NULL REFERENCES teams(id),
    away_team_id    INTEGER NOT NULL REFERENCES teams(id),
    scheduled_at    TIMESTAMP NOT NULL,
    venue           TEXT,
    status          TEXT NOT NULL DEFAULT 'NS'
                        CHECK (status IN ('NS','1H','HT','2H','FT','AET','PEN','CANC','PST')),
    home_score      INTEGER,
    away_score      INTEGER,
    season          INTEGER NOT NULL,
    broadcast       JSONB   DEFAULT '[]',
    broadcast_src   TEXT    DEFAULT 'api',
    fetched_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_matches_scheduled ON matches(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_matches_league    ON matches(league_id);
CREATE INDEX IF NOT EXISTS idx_matches_status    ON matches(status);

CREATE TABLE IF NOT EXISTS standings (
    id            SERIAL PRIMARY KEY,
    league_id     INTEGER NOT NULL REFERENCES leagues(id),
    team_id       INTEGER NOT NULL REFERENCES teams(id),
    season        INTEGER NOT NULL,
    position      INTEGER NOT NULL,
    played        INTEGER NOT NULL DEFAULT 0,
    won           INTEGER NOT NULL DEFAULT 0,
    drawn         INTEGER NOT NULL DEFAULT 0,
    lost          INTEGER NOT NULL DEFAULT 0,
    goals_for     INTEGER NOT NULL DEFAULT 0,
    goals_against INTEGER NOT NULL DEFAULT 0,
    points        INTEGER NOT NULL DEFAULT 0,
    form          TEXT,
    updated_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE (league_id, team_id, season)
);

CREATE INDEX IF NOT EXISTS idx_standings_league ON standings(league_id, season);

-- Seed leagues
INSERT INTO leagues (api_id, name, sport, country, season) VALUES
    (2,  'UEFA Champions League',        'football',   'World',        2024),
    (3,  'UEFA Europa League',           'football',   'World',        2024),
    (13, 'CONMEBOL Libertadores',        'football',   'South America',2025),
    (11, 'CONMEBOL Sul-Americana',       'football',   'South America',2025),
    (71, 'Brasileirão Série A',          'football',   'Brazil',       2025),
    (73, 'Copa do Brasil',               'football',   'Brazil',       2025),
    (12, 'NBA',                          'basketball', 'USA',          2025)
ON CONFLICT (api_id) DO NOTHING;

-- Seed teams
INSERT INTO teams (api_id, name, short_name, sport, country, tracked) VALUES
    (356,        'São Paulo FC',    'SPFC', 'football',   'Brazil',  TRUE),
    (153,        'Santos FC',       'SAN',  'football',   'Brazil',  TRUE),
    (131,        'Corinthians',     'COR',  'football',   'Brazil',  TRUE),
    (121,        'Palmeiras',       'PAL',  'football',   'Brazil',  TRUE),
    (127,        'Flamengo',        'FLA',  'football',   'Brazil',  TRUE),
    (529,        'Barcelona',       'BAR',  'football',   'Spain',   TRUE),
    (50,         'Manchester City', 'MCI',  'football',   'England', TRUE),
    (157,        'Bayern München',  'BAY',  'football',   'Germany', TRUE),
    (1610612738, 'Boston Celtics',  'BOS',  'basketball', 'USA',     TRUE)
ON CONFLICT (api_id) DO NOTHING;
