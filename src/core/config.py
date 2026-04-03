from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    This class automatically reads environment variables from the .env file.
    If a variable is missing, it falls back to the default values defined here.
    """
    app_env: str = "development"
    
    # PostgreSQL Database Settings
    postgres_user: str = "ragbot"
    postgres_password: str = "ragbot_@123"
    postgres_db: str = "ragbot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    
    # Redis Settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # Qdrant Vector Database Settings
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # RabbitMQ Settings
    rabbitmq_user: str = "ragbot"
    rabbitmq_password: str = "ragbot_@123"
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672

    # Tells Pydantic to read from the .env file in the root directory
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore" # Ignores extra variables in .env that aren't defined here
    )

    @property
    def database_url(self) -> str:
        """Constructs the async asyncpg connection URL for SQLAlchemy."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


# We use @lru_cache so that Python only reads the .env file ONCE when the app starts.
# Every time we call get_settings() after that, it returns the cached instance (super fast).
@lru_cache
def get_settings() -> Settings:
    return Settings()