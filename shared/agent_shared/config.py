from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    default_model: str = "gpt-5-nano"
    router_model: str = "gpt-5-nano"
    study_agent_model: str = "gpt-5-nano"
    quiz_agent_model: str = "gpt-5-nano"
    judge_model: str = "gpt-5-nano"
    flashcard_model: str = "gpt-5-nano"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "study"
    postgres_password: str = "study_dev_pw"
    postgres_db: str = "study_agent"

    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://study:study_dev_pw@localhost:5672/"

    circuit_breaker_fail_threshold: int = 5
    circuit_breaker_queue_depth: int = 50
    max_retries: int = 3
    eval_score_threshold: float = 7.0

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
