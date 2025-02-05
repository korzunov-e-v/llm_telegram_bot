import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    default_model: str = "claude-3-5-haiku-latest"

    bot_token = os.getenv("BOT_TOKEN")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    mongo_url = os.getenv("MONGO_URL")
    admin_token: list[int] = os.getenv("ADMIN_TOKEN", "secret-token")


settings = Settings()
