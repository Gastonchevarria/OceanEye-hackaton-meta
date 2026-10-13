"""
Modelos SQLAlchemy — persistencia de posiciones AIS y alertas
"""
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from db import Base


class VesselPosition(Base):
    """Posición AIS cruda — TimescaleDB hypertable por timestamp"""
    __tablename__ = "vessel_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mmsi: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[float] = mapped_column(Float, default=0.0)
    heading: Mapped[int] = mapped_column(Integer, default=0)
    ship_name: Mapped[str] = mapped_column(String(100), default="")
    ship_type: Mapped[int] = mapped_column(Integer, default=0)
    flag: Mapped[str] = mapped_column(String(3), default="")
    source: Mapped[str] = mapped_column(String(20), default="aisstream")

    __table_args__ = (
        Index("ix_vessel_positions_mmsi_ts", "mmsi", "timestamp"),
    )


class VesselProfile(Base):
    """Perfil acumulado por barco — se actualiza con cada posición nueva"""
    __tablename__ = "vessel_profiles"

    mmsi: Mapped[str] = mapped_column(String(9), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    flag: Mapped[str] = mapped_column(String(3), default="")
    vessel_type: Mapped[str] = mapped_column(String(50), default="")
    gfw_id: Mapped[str] = mapped_column(String(100), default="")
    last_lat: Mapped[float] = mapped_column(Float, default=0.0)
    last_lon: Mapped[float] = mapped_column(Float, default=0.0)
    last_heading: Mapped[int] = mapped_column(Integer, default=0)
    last_speed: Mapped[float] = mapped_column(Float, default=0.0)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    loitering_count: Mapped[int] = mapped_column(Integer, default=0)
    ais_gaps: Mapped[int] = mapped_column(Integer, default=0)
    port_visits: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_label: Mapped[str] = mapped_column(String(20), default="unknown")
    risk_color: Mapped[str] = mapped_column(String(10), default="#94a3b8")
    known_violations: Mapped[str] = mapped_column(Text, default="[]")
    events_summary: Mapped[str] = mapped_column(Text, default="")
    zone: Mapped[str] = mapped_column(String(100), default="South Atlantic")
    gfw_enriched: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Alert(Base):
    """Alertas generadas por comportamiento sospechoso"""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mmsi: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    vessel_name: Mapped[str] = mapped_column(String(100), default="")
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    description: Mapped[str] = mapped_column(Text, default="")
    lat: Mapped[float] = mapped_column(Float, default=0.0)
    lon: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
