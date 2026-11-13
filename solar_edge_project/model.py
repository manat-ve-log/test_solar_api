from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from DB import Base

SCHEMA = "solarEdge"


def num(precision: int, scale: int) -> Numeric:
    """NUMERIC column that returns plain float (JSON friendly) instead of Decimal."""
    return Numeric(precision, scale, asdecimal=False)


# -----------------------------
# Site  <- GET /site/{site_id}/details
# -----------------------------
class SiteDB(Base):
    __tablename__ = "sites"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="Active")
    peak_power_kw: Mapped[Optional[float]] = mapped_column(num(10, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(10))
    installation_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    equipment: Mapped[list["EquipmentDB"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    power_flows: Mapped[list["PowerFlowDB"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    energies: Mapped[list["EnergyDB"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    energy_details: Mapped[list["EnergyDetailsDB"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )


# -----------------------------
# Equipment  <- GET /equipment/{site_id}/list
# -----------------------------
class EquipmentDB(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        Index("idx_equipment_site", "site_id"),
        {"schema": SCHEMA},
    )

    serial_number: Mapped[str] = mapped_column(String(50), primary_key=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.sites.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="SolarEdge"
    )
    model: Mapped[Optional[str]] = mapped_column(String(100))
    kwp: Mapped[Optional[float]] = mapped_column(num(10, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    site: Mapped["SiteDB"] = relationship(back_populates="equipment")
    telemetries: Mapped[list["EquipmentTelemetryDB"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )


# -----------------------------
# Inverter telemetry  <- GET /equipment/{site_id}/{serial}/data
# -----------------------------
class EquipmentTelemetryDB(Base):
    __tablename__ = "equipment_telemetry"
    __table_args__ = (
        UniqueConstraint("serial_number", "recorded_at", name="uq_telemetry"),
        Index("idx_telemetry_time", "recorded_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    serial_number: Mapped[str] = mapped_column(
        String(50),
        ForeignKey(f"{SCHEMA}.equipment.serial_number", ondelete="CASCADE"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_active_power: Mapped[Optional[float]] = mapped_column(num(12, 1))  # W
    dc_voltage: Mapped[Optional[float]] = mapped_column(num(8, 1))  # V
    ground_fault_resistance: Mapped[Optional[float]] = mapped_column(num(10, 1))  # kOhm
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    equipment: Mapped["EquipmentDB"] = relationship(back_populates="telemetries")


# -----------------------------
# Current power flow  <- GET /site/{site_id}/currentPowerFlow
# -----------------------------
class PowerFlowDB(Base):
    __tablename__ = "power_flow"
    __table_args__ = (
        CheckConstraint(
            "storage_charge_level BETWEEN 0 AND 100", name="ck_power_flow_charge_level"
        ),
        Index("idx_power_flow_site_time", "site_id", text("recorded_at DESC")),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.sites.id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    update_refresh_rate: Mapped[Optional[int]] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(10), nullable=False, server_default="kW")

    pv_status: Mapped[Optional[str]] = mapped_column(String(20))
    pv_power: Mapped[Optional[float]] = mapped_column(num(10, 2))

    grid_status: Mapped[Optional[str]] = mapped_column(String(20))
    grid_power: Mapped[Optional[float]] = mapped_column(num(10, 2))

    load_status: Mapped[Optional[str]] = mapped_column(String(20))
    load_power: Mapped[Optional[float]] = mapped_column(num(10, 2))

    storage_status: Mapped[Optional[str]] = mapped_column(String(20))
    storage_power: Mapped[Optional[float]] = mapped_column(num(10, 2))
    storage_charge_level: Mapped[Optional[int]] = mapped_column(SmallInteger)
    storage_critical: Mapped[Optional[bool]] = mapped_column(Boolean)

    connections: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    site: Mapped["SiteDB"] = relationship(back_populates="power_flows")


# -----------------------------
# Energy  <- GET /site/{site_id}/energy
# -----------------------------
class EnergyDB(Base):
    __tablename__ = "energy"
    __table_args__ = (
        CheckConstraint(
            "time_unit IN ('DAY','WEEK','MONTH','YEAR')", name="ck_energy_time_unit"
        ),
        UniqueConstraint("site_id", "time_unit", "energy_date", name="uq_energy"),
        Index("idx_energy_site_date", "site_id", "energy_date"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.sites.id", ondelete="CASCADE"), nullable=False
    )
    time_unit: Mapped[str] = mapped_column(String(10), nullable=False)
    energy_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_wh: Mapped[Optional[float]] = mapped_column(num(14, 1))
    measured_by: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="INVERTER"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    site: Mapped["SiteDB"] = relationship(back_populates="energies")


# -----------------------------
# Energy details  <- GET /site/{site_id}/energyDetails
# -----------------------------
class EnergyDetailsDB(Base):
    __tablename__ = "energy_details"
    __table_args__ = (
        CheckConstraint(
            "time_unit IN ('HOUR','DAY','MONTH','YEAR')", name="ck_energy_details_time_unit"
        ),
        UniqueConstraint(
            "site_id", "meter_type", "time_unit", "recorded_at", name="uq_energy_details"
        ),
        Index("idx_energy_details_site_time", "site_id", "recorded_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.sites.id", ondelete="CASCADE"), nullable=False
    )
    meter_type: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="Production"
    )
    time_unit: Mapped[str] = mapped_column(String(10), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    value_wh: Mapped[Optional[float]] = mapped_column(num(16, 1))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    site: Mapped["SiteDB"] = relationship(back_populates="energy_details")