import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
import random
from starlette.requests import Request

from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, select, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from DB import get_db
from model import UserDB, DeviceKpiDB, DeviceListDB, StationDB, HistoryDeviceDataDB
from datetime import datetime, timedelta

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import calendar


app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)



# Custom key function to limit by username if provided in the payload, fallback to IP
def get_login_identifier(request: Request):
    # For login requests, we can try to grab the username from the request json body
    # (Note: this reads the body stream, so use with care, or key by IP for safety)
    try:
        # Slowapi allows checking request state or headers, but IP is safest for login endpoints
        return get_remote_address(request)
    except Exception:
        return get_remote_address(request)


# Token Storage
active_tokens: Dict[str, float] = {}
TOKEN_EXPIRATION_SECONDS = 30 * 60  # 30 minutes

# ---- Security Dependency ----
def verify_xsrf_token(xsrf_token: str = Header(..., alias="XSRF-TOKEN")):
    current_time = time.time()

    if xsrf_token not in active_tokens:
        raise HTTPException(
            status_code=401, detail="Invalid or expired XSRF-TOKEN"
        )

    if current_time > active_tokens[xsrf_token]:
        del active_tokens[xsrf_token]
        raise HTTPException(status_code=401, detail="XSRF-TOKEN has expired")

    return xsrf_token

# Custom handler for rate limit exceeded
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "failCode": 429,
            "message": "Too much requests",
            "data": None
        },
    )

# ---- Schemas: Login ----
class LoginRequest(BaseModel):
    userName: str
    systemCode: str


class LoginResponse(BaseModel):
    data: Optional[Any] = None
    success: bool
    failCode: int
    params: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None

# ---- Endpoint: Login ---- "//login"thirdData
@app.post("/thirdData/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    
    # 1. Query the database for the user instead of hardcoding
    db_user = db.query(UserDB).filter(UserDB.username == payload.userName).first()

    # 2. Validate user exists and system_code (password) matches
    if not db_user or db_user.systemcode != payload.systemCode:
        return LoginResponse(
            data=None,
            success=False,
            failCode=20400,
            params={"currentTime": int(time.time() * 1000)},
            message="user.login.user_or_value_invalid",
        )

    # active_tokens.clear()
    new_token = f"R-{uuid.uuid4().hex}"
    expiration_time = time.time() + TOKEN_EXPIRATION_SECONDS
    active_tokens[new_token] = expiration_time

    response.headers["XSRF-TOKEN"] = new_token

    return LoginResponse(
        data=None,
        success=True,
        failCode=0,
        params={},
        message="Northbound API Reference: https://info.support.huawei.com/******/#/u?i=UsWJrsyw&l=en_US",
    )


# ---- Schemas: Stations ----
class DataItemMap(BaseModel):
    real_health_state: str
    day_power: str
    total_power: str
    day_income: str
    month_power: str
    day_on_grid_energy: str
    day_use_energy: str
    total_income: str


class StationData(BaseModel):
    dataItemMap: DataItemMap
    stationCode: str


class QueryParams(BaseModel):
    stationCodes: str
    currentTime: int = Field(default_factory=lambda: int(time.time() * 1000))


class StationApiResponse(BaseModel):
    success: bool = True
    data: List[StationData]
    failCode: int = 0
    params: QueryParams
    message: Optional[str] = None


# ---------- Schemas (field names match the Huawei JSON exactly) ----------
class HuaweiDeviceInfo(BaseModel):
    devDn: str
    devName: str
    devTypeId: int
    esnCode: Optional[str] = None
    id: int
    invType: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    model: str
    optimizerNumber: Optional[int] = None
    softwareVersion: Optional[str] = None
    stationCode: str


class FusionParams(BaseModel):
    currentTime: Optional[int] = None
    stationCodes: Optional[str] = None


class DeviceListResponse(BaseModel):
    data: List[HuaweiDeviceInfo]
    failCode: int
    message: Optional[str] = None
    params: FusionParams
    success: bool


class DeviceListRequest(BaseModel):
    stationCodes: str

@app.post("/thirdData/getDevList", response_model=DeviceListResponse)
def get_device_list(
    body: DeviceListRequest,
    token: str = Depends(verify_xsrf_token),
    db: Session = Depends(get_db),
):
    codes = body.stationCodes.split(",")

    rows = db.execute(
        select(DeviceListDB, StationDB.station_code)
        .join(StationDB, DeviceListDB.station_id == StationDB.id)
        .where(StationDB.station_code.in_(codes))
    ).all()

    devices = [
        HuaweiDeviceInfo(
            devDn=d.dev_dn,
            devName=d.dev_name,
            devTypeId=d.dev_type_id,
            esnCode=d.esn_code,
            id=d.huawei_dev_id,
            invType=d.inv_type,
            latitude=d.latitude,
            longitude=d.longitude,
            model=d.model,
            optimizerNumber=d.optimizer_number,
            softwareVersion=d.software_version,
            stationCode=station_code,
        )
        for d, station_code in rows
    ]

    return DeviceListResponse(
        data=devices,
        failCode=0,
        message=None,
        params=FusionParams(stationCodes=body.stationCodes),
        success=True,
    )





class ParamsDevParams(BaseModel):
    devIds: str
    devTypeId: int
    currentTime: int = int(time.time() * 1000)

class DevDataItemMap(BaseModel):
   
    temperature:float
    open_time:float
    inverter_state:float
    total_cap:float
    reactive_power:float
    power_factor:float
    active_power:float
    close_time:float
    day_cap:float
    efficiency:float


class DevRealTimeItem(BaseModel):
    devID: int
    dataItemMap: DevDataItemMap

class DevRealTimeApiResponse(BaseModel):
    success: bool = True
    data: List[DevRealTimeItem]
    failCode: int = 0
    params: ParamsDevParams
    message: Optional[str] = None

class DevRealTimeRequest(BaseModel):
    devIds: str
    devTypeId: int


@app.post("/thirdData/getDevRealKpi", response_model=DevRealTimeApiResponse)
def get_realtime_device(
    payload: DevRealTimeRequest,
    token: str = Depends(verify_xsrf_token),
    db: Session = Depends(get_db),
):
    devIds = payload.devIds
    devTypeId = payload.devTypeId

    # Parse comma-separated device IDs
    device_id_list = [
        int(i.strip().strip('"').strip("'"))
        for i in devIds.split(",")
        if i.strip()
    ]

    device_items = []

    # Query database for each device
    for dev_id in device_id_list:
        db_record = (
            db.query(DeviceKpiDB)
            .filter(DeviceKpiDB.dev_id == dev_id)
            .first()
        )

        if db_record:
            data_item = DevDataItemMap(
                temperature=db_record.temperature,
                open_time=db_record.open_time,
                inverter_state=db_record.inverter_state,
                total_cap=db_record.total_cap,
                reactive_power=db_record.reactive_power,
                power_factor=db_record.power_factor,
                active_power=db_record.active_power,
                close_time=db_record.close_time,
                day_cap=db_record.day_cap,
                efficiency=db_record.efficiency,
            )

            device_items.append(
                DevRealTimeItem(
                    devID=dev_id,
                    dataItemMap=data_item,
                )
            )

    return DevRealTimeApiResponse(
        success=True,
        data=device_items,
        failCode=0,
        params=ParamsDevParams(
            devIds=devIds,
            devTypeId=devTypeId,
            currentTime=int(time.time() * 1000),
        ),
        message=None,
    )

# ---- Pydantic Schemas ----
class HistoryRequest(BaseModel):
    stationCodes: str
    collectTime: Optional[int] = None


class HistoryDataItemMap(BaseModel):
    use_power: float
    radiation_intensity: float
    reduction_total_co2: float
    reduction_total_coal: float
    theory_power: float
    ongrid_power: float
    power_profit: float
    installed_capacity: float
    buypower: float
    selfusepower: float
    pvyield:float
    perpower_ratio: float
    inverter_power: float
    reduction_total_tree: float
    performance_ratio: float


class HistoryData(BaseModel):
    stationCode: str
    collectTime: int = Field(default_factory=lambda: int(time.time() * 1000))
    dataItemMap: HistoryDataItemMap


class HistoryParams(BaseModel):
    currentTime: int = Field(default_factory=lambda: int(time.time() * 1000))
    collectTime: int = Field(default_factory=lambda: int(time.time() * 1000))
    stationCodes: str


class HistoryResponse(BaseModel):
    success: bool = True
    failCode: int = 0
    data: List[HistoryData]
    params: HistoryParams
    message: Optional[str] = None




def _subtract_months(dt: datetime, months: int) -> datetime:
    """Subtract calendar months while preserving a valid day of month."""
    month_index = dt.year * 12 + (dt.month - 1) - months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])

    return dt.replace(year=year, month=month, day=day)


def _fetch_history_data(
    payload: HistoryRequest,
    db: Session,
    interval: str = "day",
    multiplier: float = 1.0,
):
    plant_id_list = [
        s.strip().strip('"')
        for s in payload.stationCodes.split(",")
        if s.strip()
    ]

    collect_time = payload.collectTime or int(time.time() * 1000)
    target_date = datetime.fromtimestamp(collect_time / 1000.0)

    # Generate historical timestamps, including the requested end time.
    if interval == "hour":
        timestamps = [
            target_date - timedelta(hours=i)
            for i in reversed(range(24))
        ]
    elif interval == "day":
        timestamps = [
            target_date - timedelta(days=i)
            for i in reversed(range(31))
        ]
    elif interval == "month":
        timestamps = [
            _subtract_months(target_date, i)
            for i in reversed(range(12))
        ]
    else:
        raise ValueError(f"Unsupported interval: {interval}")

    history_list = []

    for station_code in plant_id_list:
        db_record = (
            db.query(HistoryDeviceDataDB)
            .filter(
                HistoryDeviceDataDB.station_code == station_code
            )
            .first()
        )

        for point_time in timestamps:
            point_collect_time = int(point_time.timestamp() * 1000)

            if db_record:
                data_map = HistoryDataItemMap(
                    use_power=(db_record.use_power or 0.0) * multiplier,
                    radiation_intensity=(db_record.radiation_intensity or 0.0 ) * multiplier,
                    reduction_total_co2=(db_record.reduction_total_co2 or 0.0 ) * multiplier,
                    reduction_total_coal=(db_record.reduction_total_coal or 0.0 ) * multiplier,
                    theory_power=(db_record.theory_power or 0.0  ) * multiplier,
                    ongrid_power=(db_record.ongrid_power or 0.0  ) * multiplier,
                    power_profit=(db_record.power_profit or 0.0  ) * multiplier,
                    installed_capacity=(db_record.installed_capacity or 0.0 ) * multiplier,
                    buypower=(db_record.buypower or 0.0) * multiplier,
                    selfusepower=(db_record.selfusepower or 0.0  ) * multiplier,
                    pvyield=(db_record.pvyield or 0.0) * multiplier,
                    perpower_ratio=(db_record.perpower_ratio or 0.0 ) * multiplier,
                    inverter_power=(db_record.inverter_power or 0.0 ) * multiplier,
                    reduction_total_tree=(db_record.reduction_total_tree or 0.0 ) * multiplier,
                    performance_ratio=(db_record.performance_ratio or 0.0 ) * multiplier,
                )
            else:
                # Mock data: values are generated independently
                # for each station and timestamp.
                data_map = HistoryDataItemMap(
                    use_power=round(random.uniform(20, 60), 2) * multiplier,
                    radiation_intensity=round(random.uniform(0, 24), 2) * multiplier,
                    reduction_total_co2=round(random.uniform(1, 10), 2) * multiplier,
                    reduction_total_coal=round(random.uniform(1000, 5000), 2) * multiplier,
                    theory_power=round(random.uniform(0, 100), 2) * multiplier,
                    ongrid_power=round(random.uniform(0.85, 0.99), 2) * multiplier,
                    power_profit=round(random.uniform(50, 500), 2) * multiplier,
                    installed_capacity=round(random.uniform(0, 24), 2) * multiplier,
                    buyPower=round(random.uniform(0, 24), 2) * multiplier,
                    selfUsePower=round(random.uniform(0, 24), 2) * multiplier,
                    PVYield=round(random.uniform(0, 24), 2 ) * multiplier,
                    perpower_ratio=round(random.uniform(10, 100), 2) * multiplier,
                    inverter_power=round(random.uniform(95, 99.5), 2) * multiplier,
                    reduction_total_tree=round(random.uniform(95, 99.5), 2) * multiplier,
                    performance_ratio=round(random.uniform(95, 99.5), 2) * multiplier,
                )

            history_list.append(
                HistoryData(
                    stationCode=station_code,
                    collectTime=point_collect_time,
                    dataItemMap=data_map,
                )
            )

    return HistoryResponse(
        success=True,
        failCode=0,
        data=history_list,
        params=HistoryParams(
            stationCodes=payload.stationCodes,
            collectTime=collect_time,
            currentTime=int(time.time() * 1000),
        ),
        message=None,
    )

@app.post("/thirdData/getKpiStationHour", response_model=HistoryResponse)
def get_history_hourly_plant(
    payload: HistoryRequest,
    token: str = Depends(verify_xsrf_token),
    db: Session = Depends(get_db),
):
    return _fetch_history_data(payload, db, interval="hour")


@app.post("/thirdData/getKpiStationDay", response_model=HistoryResponse)
def get_history_daily_plant(
    payload: HistoryRequest,
    token: str = Depends(verify_xsrf_token),
    db: Session = Depends(get_db),
):
    return _fetch_history_data(payload, db, interval="day")


@app.post("/thirdData/getKpiStationMonth", response_model=HistoryResponse)
def get_history_monthly_plant(
    payload: HistoryRequest,
    token: str = Depends(verify_xsrf_token),
    db: Session = Depends(get_db),
):
    return _fetch_history_data(payload, db, interval="month")

@app.post("/thirdData/getKpiStationYear", response_model=HistoryResponse)
def get_history_monthly_plant(
    payload: HistoryRequest,
    token: str = Depends(verify_xsrf_token),
    db: Session = Depends(get_db),
):
    return _fetch_history_data(payload, db, interval="year")