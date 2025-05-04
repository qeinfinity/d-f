#### 1 `dealer_flow/config.py`
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Web-socket & REST hosts
    deribit_ws: str = "wss://www.deribit.com/ws/api/v2"
    deribit_rest: str = "https://www.deribit.com/api/v2"

    # OAuth2 creds (set in .env)
    deribit_id: str
    deribit_secret: str

    # Redis
    redis_url: str = "redis://:changeme@redis:6379/0"

    # General
    currency: str = "BTC"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"


settings = Settings()
