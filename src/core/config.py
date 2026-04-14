from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration — reads every value from environment variables (or .env).
    Add a field here and it's automatically available everywhere via get_settings().
    """

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = "development"
    app_secret_key: str = ""        # RS256 private key PEM — required in production
    app_public_key: str = ""        # RS256 public key PEM  — required in production
    app_cors_origins: str = "http://localhost:3000"

    # ── PostgreSQL (SQLAlchemy / asyncpg) ─────────────────────────────────────
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_db: str = "postgres"
    postgres_host: str = "pg-database.cxekc0wmoulk.ap-south-1.rds.amazonaws.com"
    postgres_port: int = 5432
    postgres_ssl: bool = True        # True → asyncpg uses verify-full SSL (RDS)
    postgres_ssl_cert: str = "./global-bundle.pem"   # path to RDS CA bundle
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # ── RabbitMQ ──────────────────────────────────────────────────────────────
    rabbitmq_user: str = "ragbot"
    rabbitmq_password: str = "ragbot_@123"
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_vhost: str = "/"
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""        # Only needed for Qdrant Cloud

    # ── AWS RDS (psycopg2 direct connection) ──────────────────────────────────
    rds_host: str = "pg-database.cxekc0wmoulk.ap-south-1.rds.amazonaws.com"
    rds_port: int = 5432
    rds_db: str = "postgres"
    rds_user: str = "postgres"
    rds_db_password: str = ""          # plaintext — dev/test only
    rds_secret_name: str = ""          # AWS Secrets Manager secret name (prod)
    rds_ssl_cert: str = "./global-bundle.pem"

    # ── AWS S3 ────────────────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    s3_bucket_name: str = "ragbot-files"
    s3_presigned_url_ttl: int = 3600

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-large"
    openai_default_model: str = "gpt-4o"

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""

    # ── Cohere ────────────────────────────────────────────────────────────────
    cohere_api_key: str = ""

    # ── LangSmith ─────────────────────────────────────────────────────────────
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "ragbot-production"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "text"        # text for dev, json for prod

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """Async asyncpg connection URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.app_cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance — .env is read only once at startup."""
    return Settings()
