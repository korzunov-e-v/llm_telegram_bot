from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    default_temperature: float = Field(0.7)
    default_max_tokens: int = Field(4096)
    default_model: str = Field("claude-3-5-haiku-latest")

    bot_token: str = Field()
    anthropic_api_key: str = Field()
    mongo_url: str = Field()
    admin_token: str = Field("secret-token")
    debug: bool = Field(False)


settings = Settings()
