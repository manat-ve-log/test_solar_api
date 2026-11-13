from sqlalchemy import Column, Integer, String, Float
from DB import Base
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime,  ForeignKey,  func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UserDB(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "solar"}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    systemcode = Column(String)  # Match the exact database column name without underscore




class DeviceKpiDB(Base):
    __tablename__ = "realtimedevicedata"
    __table_args__ = {"schema": "solar"}

    recorded_at = Column(DateTime(timezone=True), primary_key=True)
    dev_id = Column(Integer, primary_key=True, index=True)
    temperature = Column(Float)
    open_time = Column(Float)
    inverter_state = Column(Float)
    total_cap = Column(Float)
    reactive_power = Column(Float)
    power_factor = Column(Float)
    active_power = Column(Float)
    close_time = Column(Float)
    day_cap = Column(Float)
    efficiency = Column(Float)



class DeviceListDB(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "solar"}

    dev_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # SERIAL
    station_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("solar.stations.id", ondelete="CASCADE"),
        nullable=True,  # your DDL has no NOT NULL
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # CURRENT_TIMESTAMP
    )

    # Huawei fields
    huawei_dev_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    dev_dn: Mapped[str] = mapped_column(String, nullable=False)
    dev_name: Mapped[str] = mapped_column(String, nullable=False)
    dev_type_id: Mapped[int] = mapped_column(Integer, nullable=False)
    esn_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    inv_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    optimizer_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    software_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    station: Mapped[Optional["StationDB"]] = relationship(back_populates="devices")



class StationDB(Base):
    __tablename__ = "stations"
    __table_args__ = {"schema": "solar"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    station_code: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    station_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Back-populate relationship to devices
    devices: Mapped[list["DeviceListDB"]] = relationship(back_populates="station", cascade="all, delete")



class HistoryDeviceDataDB(Base):
    __tablename__ = "historydevicedata"
    __table_args__ = {"schema": "solar"}

    recorded_at = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    station_code = Column(String(100), primary_key=True, index=True)
    use_power = Column(Float)
    radiation_intensity = Column(Float)
    reduction_total_co2 = Column(Float)
    reduction_total_coal = Column(Float)
    theory_power = Column(Float)
    ongrid_power = Column(Float)
    power_profit = Column(Float)
    installed_capacity = Column(Float)

    # Match the exact lowercase names shown in your psql output
    buypower: Optional[float] = 0.0
    selfusepower: Optional[float] = 0.0
    pvyield: Optional[float] = 0.0

    perpower_ratio = Column(Float)
    inverter_power = Column(Float)
    reduction_total_tree = Column(Float)
    performance_ratio = Column(Float)