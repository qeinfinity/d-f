#### 1 `dealer_flow/config.py`
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Web-socket & REST hosts
    deribit_ws: str = "wss://www.deribit.com/ws/api/v2"
    deribit_rest: str = "https://www.deribit.com/api/v2"

    # OAuth2 creds (set in .env)
    deribit_id: str = "lIdRCJdl"
    deribit_secret: str = "BiqWyPz855okyEBIaSFYre4vAXQ7t1az1pETWE36Dwo"

    # Redis
    redis_url: str = "redis://:changeme@redis:6379/0"

    deribit_max_auth_instruments: int = 100

    # General
    currency: str = "BTC"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"


settings = Settings()
