from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Messenger AI"
    host: str = "0.0.0.0"
    port: int = 8080
    public_base_url: str = ""
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR / 'messenger.db'}"
    )
    testing: bool = False
    auto_reply_enabled: bool = True

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ai_system_prompt: str = (
        "Ты вежливый ассистент компании. Отвечай кратко, по делу и на языке клиента. "
        "Не выдумывай факты, цены, сроки и статусы заказов, которых нет в истории переписки. "
        "Если вопрос требует человека (возврат денег, жалоба, юридический вопрос, "
        "нестандартная ситуация) — вежливо скажи, что передашь специалисту."
    )
    ai_history_limit: int = 12

    telegram_bot_token: str = ""
    telegram_owner_chat_id: str = ""
    telegram_webhook_secret: str = "messenger-ai-telegram"

    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_owner_phone: str = ""

    instagram_access_token: str = ""
    instagram_account_id: str = ""
    instagram_owner_igsid: str = ""

    meta_verify_token: str = "messenger-ai-verify"
    meta_app_secret: str = ""

    report_hour: int = 20
    report_timezone: str = "Europe/Moscow"
    company_name: str = "Компания"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id)

    @property
    def instagram_enabled(self) -> bool:
        return bool(self.instagram_access_token and self.instagram_account_id)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def owner_channel_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_owner_chat_id)


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
