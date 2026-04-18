from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base


class League(Base):
    __tablename__ = "leagues"
    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    sport      = Column(String, nullable=False)
    country    = Column(String)
    api_id     = Column(Integer, unique=True)
    season     = Column(Integer, nullable=False)
    logo_url   = Column(String)
    matches    = relationship("Match", back_populates="league")
    standings  = relationship("Standing", back_populates="league")


class Team(Base):
    __tablename__ = "teams"
    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    short_name = Column(String)
    sport      = Column(String, nullable=False)
    api_id     = Column(Integer, unique=True)
    logo_url   = Column(String)
    country    = Column(String)
    tracked    = Column(Boolean, default=False)


class Match(Base):
    __tablename__ = "matches"
    id           = Column(Integer, primary_key=True)
    api_id       = Column(Integer, unique=True)
    sport        = Column(String, nullable=False)
    league_id    = Column(Integer, ForeignKey("leagues.id"), nullable=False)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    venue        = Column(String)
    status       = Column(String, default="NS")
    home_score   = Column(Integer)
    away_score   = Column(Integer)
    season       = Column(Integer, nullable=False)
    broadcast    = Column(String, default="[]")
    broadcast_src = Column(String, default="api")
    fetched_at   = Column(DateTime)
    league       = relationship("League", back_populates="matches")
    home_team    = relationship("Team", foreign_keys=[home_team_id])
    away_team    = relationship("Team", foreign_keys=[away_team_id])


class Standing(Base):
    __tablename__ = "standings"
    id            = Column(Integer, primary_key=True)
    league_id     = Column(Integer, ForeignKey("leagues.id"), nullable=False)
    team_id       = Column(Integer, ForeignKey("teams.id"), nullable=False)
    season        = Column(Integer, nullable=False)
    position      = Column(Integer, nullable=False)
    played        = Column(Integer, default=0)
    won           = Column(Integer, default=0)
    drawn         = Column(Integer, default=0)
    lost          = Column(Integer, default=0)
    goals_for     = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    points        = Column(Integer, default=0)
    form          = Column(String)
    league        = relationship("League", back_populates="standings")
    team          = relationship("Team")
