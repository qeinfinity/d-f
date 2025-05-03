from pathlib import Path
from pydantic import BaseSettings

class Settings(BaseSettings):
    deribit_ws: str = "wss://www.deribit.com/ws/api/v2"
    redis_url: str = "redis://localhost:6379/0"
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 9000
    currency: str = "BTC"
    
    class Config:
        env_file = Path(__file__).parent.parent / ".env"

settings = Settings()
