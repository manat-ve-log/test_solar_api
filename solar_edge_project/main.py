import math
import random
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
import calendar
from DB import get_db
from model import (
    EnergyDB,
    EnergyDetailsDB,
    EquipmentDB,
    EquipmentTelemetryDB,
    PowerFlowDB,
    SiteDB,
)

app = FastAPI()

# -----------------------------
# SolarEdge Mock API (random data, saved to PostgreSQL)
# -----------------------------
MOCK_API_KEY = "NRTYUIOOUHUFEYHJFRKFORI123KLDFOFIFOIEMEFSKIJSORIJ"
SITE_CODE = 1234567
CHUNK = 1000  # rows per INSERT (keeps under PostgreSQL's parameter limit)


def check_api_key(api_key: str = Query(...)):
    if api_key != MOCK_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


class SolarEdgeEquipment(BaseModel):
    name: str
    manufacturer: str = "SolarEdge"
    model: str = "SE33.3K"
    serialNumber: str
    kWp: float = 33.0


# Equipment list stays fixed (it is static metadata, not measurements)
SOLAREDGE_EQUIPMENT = [
    {"name": "Inverter 1", "manufacturer": "SolarEdge", "model": "SE33.3K",
     "serialNumber": "SE12345678", "kWp": 33.0},
    {"name": "Inverter 2", "manufacturer": "SolarEdge", "model": "SE27.6K",
     "serialNumber": "SE87654321", "kWp": 27.6},
]

SITE_DETAILS = {
    "name": "Mock SolarEdge Site",
    "status": "Active",
    "peakPower": 33.0,
    "currency": "THB",
    "installationDate": "2025-01-01",
    "notes": "Mock site for testing",
}


# -----------------------------
# Random helpers
# -----------------------------
def solar_factor(dt: datetime) -> float:
    """Bell curve 0..1: zero at night, peak around noon (06:00-18:00)."""
    hour = dt.hour + dt.minute / 60
    if hour < 6 or hour > 18:
        return 0.0
    return math.sin(math.pi * (hour - 6) / 12)


def parse_dt(value: str):
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# -----------------------------
# DB helpers
# -----------------------------
def bulk_upsert(db: Session, model, rows: list[dict], conflict_cols: list[str],
                update_cols: list[str] | None = None):
    """INSERT ... ON CONFLICT (update_cols given -> DO UPDATE, else DO NOTHING)."""
    for i in range(0, len(rows), CHUNK):
        stmt = insert(model).values(rows[i:i + CHUNK])
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={c: stmt.excluded[c] for c in update_cols},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
        db.execute(stmt)


def save_site(db: Session, site_id: int, update: bool = False):
    d = SITE_DETAILS
    row = {
        "id": site_id,
        "name": d["name"],
        "status": d["status"],
        "peak_power_kw": d["peakPower"],
        "currency": d["currency"],
        "installation_date": date.fromisoformat(d["installationDate"]),
        "notes": d["notes"],
    }
    bulk_upsert(
        db, SiteDB, [row], ["id"],
        update_cols=["name", "status", "peak_power_kw", "currency",
                     "installation_date", "notes"] if update else None,
    )


def save_equipment(db: Session, site_id: int):
    save_site(db, site_id)  # FK: site must exist first
    rows = [
        {
            "serial_number": e["serialNumber"],
            "site_id": site_id,
            "name": e["name"],
            "manufacturer": e["manufacturer"],
            "model": e["model"],
            "kwp": e["kWp"],
        }
        for e in SOLAREDGE_EQUIPMENT
    ]
    bulk_upsert(db, EquipmentDB, rows, ["serial_number"],
                update_cols=["name", "manufacturer", "model", "kwp"])


# -----------------------------
# Endpoints
# -----------------------------
@app.get("/site/{site_id}/details")
def get_solaredge_site_details(
    site_id: int,
    api_key: str = Depends(check_api_key),
    db: Session = Depends(get_db),
):
    save_site(db, site_id, update=True)
    db.commit()
    return {"details": {"id": site_id, **SITE_DETAILS}}


@app.get("/equipment/{site_id}/list")
def get_solaredge_equipment(
    site_id: int,
    api_key: str = Depends(check_api_key),
    db: Session = Depends(get_db),
):
    save_equipment(db, site_id)
    db.commit()
    return {"reporters": SOLAREDGE_EQUIPMENT}


@app.get("/equipment/{site_id}/{serial_number}/data")
def get_solaredge_equipment_data(
    site_id: int,
    serial_number: str,
    startTime: str = Query(...),
    endTime: str = Query(...),
    api_key: str = Depends(check_api_key),
    db: Session = Depends(get_db),
):
    equipment = next(
        (i for i in SOLAREDGE_EQUIPMENT if i["serialNumber"] == serial_number), None
    )
    if equipment is None:
        return {"data": {"count": 0, "telemetries": []}}

    start, end = parse_dt(startTime), parse_dt(endTime)
    max_power = equipment["kWp"] * 1000  # W

    telemetries = []
    rows = []
    if start and end and start <= end:
        # One sample every 5 minutes, capped to avoid huge responses
        current = start
        while current <= end and len(telemetries) < 300:
            f = solar_factor(current)
            power = round(max_power * f * random.uniform(0.6, 0.95), 1)
            dc = round(random.uniform(700, 800) if f > 0 else 0.0, 1)
            gfr = round(random.uniform(900, 1100), 1)
            telemetries.append({
                "date": current.strftime("%Y-%m-%d %H:%M:%S"),
                "totalActivePower": power,
                "dcVoltage": dc,
                "groundFaultResistance": gfr,
            })
            rows.append({
                "serial_number": serial_number,
                "recorded_at": current.replace(tzinfo=None),
                "total_active_power": power,
                "dc_voltage": dc,
                "ground_fault_resistance": gfr,
            })
            current += timedelta(minutes=5)

        # Only valid timestamps are stored
        save_equipment(db, site_id)
        bulk_upsert(
            db, EquipmentTelemetryDB, rows, ["serial_number", "recorded_at"],
            update_cols=["total_active_power", "dc_voltage", "ground_fault_resistance"],
        )
        db.commit()
    else:
        # Unparseable dates: return a few random points using the raw strings (not stored)
        for d in (startTime, startTime, endTime):
            telemetries.append({
                "date": d,
                "totalActivePower": round(random.uniform(5000, max_power), 1),
                "dcVoltage": round(random.uniform(700, 800), 1),
                "groundFaultResistance": round(random.uniform(900, 1100), 1),
            })

    return {"data": {"count": len(telemetries), "telemetries": telemetries}}


@app.get("/site/{site_id}/currentPowerFlow")
def get_solaredge_current_power_flow(
    site_id: int,
    api_key: str = Depends(check_api_key),
    db: Session = Depends(get_db),
):
    pv = round(random.uniform(0, 30) * solar_factor(datetime.now()), 2)
    load = round(random.uniform(3, 15), 2)
    grid = round(max(load - pv, 0.0), 2)  # grid covers the shortfall
    charge = random.randint(10, 100)

    connections = []
    if grid > 0:
        connections.append({"from": "GRID", "to": "Load"})
    if pv > 0:
        connections.append({"from": "PV", "to": "Load"})

    result = {
        "siteCurrentPowerFlow": {
            "updateRefreshRate": 3,
            "unit": "kW",
            "connections": connections,
            "GRID": {"status": "Active" if grid > 0 else "Idle", "currentPower": grid},
            "LOAD": {"status": "Active", "currentPower": load},
            "PV": {"status": "Active" if pv > 0 else "Idle", "currentPower": pv},
            "STORAGE": {
                "status": "Idle",
                "currentPower": 0.0,
                "chargeLevel": charge,
                "critical": False,
            },
        }
    }

    s = result["siteCurrentPowerFlow"]
    save_site(db, site_id)
    db.add(PowerFlowDB(
        site_id=site_id,
        update_refresh_rate=s["updateRefreshRate"],
        unit=s["unit"],
        pv_status=s["PV"]["status"],
        pv_power=s["PV"]["currentPower"],
        grid_status=s["GRID"]["status"],
        grid_power=s["GRID"]["currentPower"],
        load_status=s["LOAD"]["status"],
        load_power=s["LOAD"]["currentPower"],
        storage_status=s["STORAGE"]["status"],
        storage_power=s["STORAGE"]["currentPower"],
        storage_charge_level=s["STORAGE"]["chargeLevel"],
        storage_critical=s["STORAGE"]["critical"],
        connections=connections,
    ))
    db.commit()
    return result


# def add_months(source_date: date, months: int) -> date:
#     month = source_date.month - 1 + months
#     year = source_date.year + month // 12
#     month = month % 12 + 1

#     day = min(
#         source_date.day,
#         calendar.monthrange(year, month)[1]
#     )

#     return date(year, month, day)

@app.get("/site/{site_id}/energy")
def get_solaredge_energy(
    site_id: int,
    timeUnit: str = Query("DAY", pattern="^(DAY|HOUR)$"),
    startDate: date = Query(...),
    endDate: date = Query(...),
    api_key: str = Depends(check_api_key),
    db: Session = Depends(get_db),
):
    if startDate > endDate:
        raise HTTPException(
            status_code=400,
            detail="startDate must be before or equal to endDate"
        )

   # Validate SolarEdge API time range limitations
    max_end_date = None

    if timeUnit == "DAY":
        next_year = startDate.year + 1

        max_end_date = date(
            next_year,
            startDate.month,
            min(
                startDate.day,
                calendar.monthrange(next_year, startDate.month)[1]
            )
    )

    elif timeUnit == "HOUR":
        max_end_date = add_months(startDate, 1)

    if max_end_date is not None and endDate > max_end_date:
        raise HTTPException(
            status_code=400,
            detail=f"For timeUnit={timeUnit}, the maximum date range has been exceeded."
        )

    ranges = {
        "YEAR": (150000.0, 220000.0),
        "MONTH": (12000.0, 18000.0),
        "HOUR": (10.0, 50.0),
        "DAY": (100.0, 400.0),
    }

    lo, hi = ranges[timeUnit]

    rows = []
    values = []

    # Generate hourly records
    if timeUnit == "HOUR":
        current = datetime.combine(startDate, datetime.min.time())
        end = datetime.combine(endDate, datetime.min.time())

        while current <= end:
            for hour in range(24):
                recorded_at = current + timedelta(hours=hour)

                value = round(random.uniform(lo, hi), 1)

                values.append({
                    "date": recorded_at.isoformat(),
                    "value": value,
                })

                rows.append({
                    "site_id": site_id,
                    "meter_type": "Production",
                    "time_unit": timeUnit,
                    "recorded_at": recorded_at,
                    "value_wh": value,
                })

            current += timedelta(days=1)

    # Generate daily records for other time units
    else:
        current = startDate

        while current <= endDate:
            value = round(random.uniform(lo, hi), 1)

            values.append({
                "date": current.isoformat(),
                "value": value,
            })

            rows.append({
                "site_id": site_id,
                "meter_type": "Production",
                "time_unit": timeUnit,
                "recorded_at": datetime.combine(
                    current,
                    datetime.min.time()
                ),
                "value_wh": value,
            })

            current += timedelta(days=1)

    save_site(db, site_id)

    bulk_upsert(
        db,
        EnergyDetailsDB,
        rows,
        ["site_id", "meter_type", "time_unit", "recorded_at"],
        update_cols=["value_wh"],
    )

    db.commit()

    return {
        "energy": {
            "timeUnit": timeUnit,
            "unit": "Wh",
            "measuredBy": "INVERTER",
            "values": values,
        }
    }







# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def add_months(dt: datetime, months: int) -> datetime:
    """Add calendar months while handling shorter months."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1

    day = min(
        dt.day,
        calendar.monthrange(year, month)[1],
    )

    return dt.replace(year=year, month=month, day=day)


def add_years(dt: datetime, years: int) -> datetime:
    """Add calendar years while handling leap days."""
    year = dt.year + years
    day = min(
        dt.day,
        calendar.monthrange(year, dt.month)[1],
    )

    return dt.replace(year=year, day=day)


def get_start_date(dt: datetime, time_unit: str) -> datetime:
    """Align a datetime to the beginning of its interval."""

    if time_unit == "QUARTER_OF_AN_HOUR":
        minute = (dt.minute // 15) * 15
        return dt.replace(
            minute=minute,
            second=0,
            microsecond=0,
        )

    if time_unit == "HOUR":
        return dt.replace(
            minute=0,
            second=0,
            microsecond=0,
        )

    if time_unit == "DAY":
        return dt.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    if time_unit == "WEEK":
        monday = dt - timedelta(days=dt.weekday())
        return monday.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    if time_unit == "MONTH":
        return dt.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    if time_unit == "YEAR":
        return dt.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    raise ValueError(f"Unsupported time unit: {time_unit}")


def get_next_date(dt: datetime, time_unit: str) -> datetime:
    """Advance a datetime by one interval."""

    if time_unit == "QUARTER_OF_AN_HOUR":
        return dt + timedelta(minutes=15)

    if time_unit == "HOUR":
        return dt + timedelta(hours=1)

    if time_unit == "DAY":
        return dt + timedelta(days=1)

    if time_unit == "WEEK":
        return dt + timedelta(weeks=1)

    if time_unit == "MONTH":
        return add_months(dt, 1)

    if time_unit == "YEAR":
        return add_years(dt, 1)

    raise ValueError(f"Unsupported time unit: {time_unit}")


def generate_energy_value(meter_type: str, dt: datetime) -> int:
    """Generate mock energy values in Wh."""

    hour = dt.hour

    is_night = hour < 6 or hour >= 19

    if is_night:
        if meter_type in ("Production", "FeedIn", "SelfConsumption"):
            return 0


    ranges = {
        "Production": (1000, 30000),
        "Consumption": (1000, 30000),
        "Purchased": (500, 15000),
        "SelfConsumption": (500, 20000),
        "FeedIn": (500, 20000),
    }

    minimum, maximum = ranges.get(
        meter_type,
        (1000, 30000),
    )

    return random.randint(minimum, maximum)


# --------------------------------------------------
# Energy Details Endpoint
# --------------------------------------------------

@app.get("/site/{site_id}/energyDetails")
def get_energy_details(
    site_id: int,
    # meters: str = Query(
    #     default="PRODUCTION,CONSUMPTION,SELFCONSUMPTION",
    #     description=(
    #         "Comma-separated meters: PRODUCTION, CONSUMPTION, "
    #         "PURCHASED, SELFCONSUMPTION, FEEDIN"
    #     ),
    # ),
    timeUnit: str = Query(
        default="WEEK",
        pattern=(
            "^(QUARTER_OF_AN_HOUR|HOUR|DAY|WEEK|MONTH|YEAR)$"
        ),
    ),
    startTime: datetime = Query(...),
    endTime: datetime = Query(...),
    api_key: str = Depends(check_api_key),
):
    # Validate date range
    if startTime > endTime:
        raise HTTPException(
            status_code=400,
            detail="startTime must be before or equal to endTime",
        )

    # Map API meter names to response names
    meter_mapping = {
        "PRODUCTION": "Production",
        "CONSUMPTION": "Consumption",
        "PURCHASED": "Purchased",
        "SELFCONSUMPTION": "SelfConsumption",
        "FEEDIN": "FeedIn",
    }

    # Parse requested meters
    requested_meters = [
        meter.strip().upper()
        for meter in ["Production","Consumption","Purchased","SelfConsumption","FeedIn"]
        if meter.strip()
    ]

    if not requested_meters:
        raise HTTPException(
            status_code=400,
            detail="At least one meter must be specified",
        )

    # Validate meter names
    invalid_meters = [
        meter
        for meter in requested_meters
        if meter not in meter_mapping
    ]

    if invalid_meters:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid meters: {invalid_meters}",
        )

    # Align the first result to the selected interval
    current = get_start_date(startTime, timeUnit)

    meter_results = []

    for meter in requested_meters:
        meter_type = meter_mapping[meter]
        values = []

        current = get_start_date(startTime, timeUnit)

        while current <= endTime:
            values.append({
                "date": current.strftime("%Y-%m-%d %H:%M:%S"),
                "value": generate_energy_value(meter_type, current),
            })

            current = get_next_date(current, timeUnit)

        meter_results.append({
            "type": meter_type,
            "values": values,
        })

    return {
        "energyDetails": {
            "timeUnit": timeUnit,
            "unit": "Wh",
            "meters": meter_results,
        }
    }