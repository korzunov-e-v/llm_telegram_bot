from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmProviderType(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    default_temperature: float = Field(0.7)
    default_max_tokens: int = Field(4096)
    default_model: str = Field("openai/gpt-4.1-mini")

    bot_token: str = Field()
    llm_api_key: str = Field()
    mongo_url: str = Field()
    admin_token: str = Field("secret-token")
    llm_provider_type: LlmProviderType = Field(LlmProviderType.OPENAI)
    model_cache_ttl_sec: int = Field(5 * 60)
    extra_headers: dict | None = Field(None)
    debug: bool = Field(False)


settings = Settings()
