import pytest

from messenger_ai.app import build_runtime, create_app
from messenger_ai.config import Settings
from messenger_ai.db import init_db


@pytest.fixture
def settings() -> Settings:
    return Settings(
        testing=True,
        database_url="sqlite+aiosqlite:///:memory:",
        openai_api_key="",
        telegram_bot_token="",
        telegram_owner_chat_id="100",
        whatsapp_token="",
        instagram_access_token="",
        meta_verify_token="verify-me",
        meta_app_secret="meta-secret",
        company_name="Тестовая компания",
        auto_reply_enabled=True,
    )


@pytest.fixture
async def runtime(settings):
    rt = build_runtime(settings)
    await init_db(rt.engine)
    yield rt
    await rt.engine.dispose()


@pytest.fixture
def app(runtime):
    return create_app(runtime.settings, runtime)
