"""Settings read once from the environment or `.env`."""

from functools import cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Every tunable value, with a default that runs the demo."""

    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / "langfuse.env"), env_ignore_empty=True, extra="ignore"
    )

    openai_api_key: SecretStr | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_url: str = Field("http://127.0.0.1:3000", description="Self-hosted Langfuse for traces, scores and evals")
    langfuse_pause: float = Field(60.0, description="Seconds to stop calling Langfuse after it fails to answer")
    model: str = Field("gpt-6-luna", description="OpenAI model for reading cases and writing replies")
    output_retries: int = Field(2, description="Times a model may correct an output the checks reject")
    timeout: float = Field(1.0, description="Seconds each call to an HR system may take")
    retries: int = Field(1, description="Extra attempts after a timed-out call")
    fault_delay: float = Field(5.0, description="Seconds a system told to fail hangs for")
    data: Path = Field(
        ROOT / "data",
        description="Tenant policies and mock HR systems, one folder per tenant",
    )
    confidence: float = Field(0.95, description="Confidence level of the error-rate bounds the eval reports")
    eval_concurrency: int = Field(4, description="Eval cases run at once")
    database: Path = Field(ROOT / "cases.sqlite", description="Case log and executed actions")


@cache
def settings() -> Settings:
    """The process-wide settings."""
    return Settings()
