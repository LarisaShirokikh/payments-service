from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = "secret-api-key"

    postgres_user: str = "payments"
    postgres_password: str = "payments"
    postgres_db: str = "payments"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    process_min_seconds: float = 2
    process_max_seconds: float = 5
    success_rate: float = 0.9

    webhook_max_attempts: int = 3
    webhook_backoff_base_seconds: float = 1
    webhook_timeout_seconds: float = 10

    outbox_poll_interval_seconds: float = 1
    outbox_batch_size: int = 50

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
