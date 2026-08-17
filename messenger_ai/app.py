from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from messenger_ai.adapters import (
    FakeAdapter,
    InstagramAdapter,
    TelegramAdapter,
    WhatsAppAdapter,
    parse_instagram_payload,
    parse_meta_payload,
    parse_telegram_update,
    parse_whatsapp_payload,
)
from messenger_ai.adapters.base import ChannelAdapter
from messenger_ai.ai import AIClient
from messenger_ai.config import Settings
from messenger_ai.db import create_engine, create_session_factory, init_db
from messenger_ai.models import Conversation, Message, Report
from messenger_ai.pipeline import Pipeline
from messenger_ai.reports import ReportService
from messenger_ai.schemas import IncomingMessage
from messenger_ai.security import verify_meta_signature

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

CHANNEL_LABELS = {
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
}


@dataclass
class Runtime:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    adapters: dict[str, ChannelAdapter]
    ai: AIClient
    pipeline: Pipeline
    reports: ReportService
    scheduler: AsyncIOScheduler | None = None
    poll_task: asyncio.Task | None = None
    telegram_offset: int = 0


def build_runtime(settings: Settings, http_client=None) -> Runtime:
    engine = create_engine(settings.database_url, testing=settings.testing)
    session_factory = create_session_factory(engine)
    adapters: dict[str, ChannelAdapter] = {}
    telegram = TelegramAdapter(
        settings.telegram_bot_token,
        settings.telegram_owner_chat_id,
        client=http_client,
    )
    whatsapp = WhatsAppAdapter(
        settings.whatsapp_token,
        settings.whatsapp_phone_number_id,
        settings.whatsapp_owner_phone,
        client=http_client,
    )
    instagram = InstagramAdapter(
        settings.instagram_access_token,
        settings.instagram_account_id,
        settings.instagram_owner_igsid,
        client=http_client,
    )
    if settings.testing or not telegram.enabled:
        adapters["telegram"] = FakeAdapter("telegram", "Telegram")
    else:
        adapters["telegram"] = telegram
    if settings.testing or not whatsapp.enabled:
        adapters["whatsapp"] = FakeAdapter("whatsapp", "WhatsApp")
    else:
        adapters["whatsapp"] = whatsapp
    if settings.testing or not instagram.enabled:
        adapters["instagram"] = FakeAdapter("instagram", "Instagram")
    else:
        adapters["instagram"] = instagram

    ai = AIClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        system_prompt=settings.ai_system_prompt,
        company_name=settings.company_name,
        client=http_client,
    )
    reports = ReportService(
        session_factory,
        adapters,
        ai,
        timezone_name=settings.report_timezone,
    )

    async def report_callback(kind: str = "report") -> str:
        if kind == "stats":
            return await reports.short_stats()
        report = await reports.build_report(deliver=False)
        return report.body_html

    pipeline = Pipeline(
        session_factory,
        adapters,
        ai,
        auto_reply_default=settings.auto_reply_enabled,
        history_limit=settings.ai_history_limit,
        report_callback=report_callback,
    )
    return Runtime(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        adapters=adapters,
        ai=ai,
        pipeline=pipeline,
        reports=reports,
    )


def create_app(settings: Settings | None = None, runtime: Runtime | None = None) -> FastAPI:
    settings = settings or Settings()
    runtime = runtime or build_runtime(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await init_db(runtime.engine)
        if not settings.testing:
            scheduler = AsyncIOScheduler(timezone=settings.report_timezone)
            scheduler.add_job(
                _daily_report,
                CronTrigger(hour=settings.report_hour, minute=0),
                args=[runtime],
                id="daily_report",
                replace_existing=True,
            )
            scheduler.start()
            runtime.scheduler = scheduler
            telegram = runtime.adapters.get("telegram")
            if (
                isinstance(telegram, TelegramAdapter)
                and telegram.enabled
                and not settings.public_base_url
            ):
                runtime.poll_task = asyncio.create_task(_poll_telegram(runtime))
            elif (
                isinstance(telegram, TelegramAdapter)
                and telegram.enabled
                and settings.public_base_url
            ):
                webhook = settings.public_base_url.rstrip("/") + "/webhook/telegram"
                await telegram.set_webhook(webhook, settings.telegram_webhook_secret)
        yield
        if runtime.poll_task:
            runtime.poll_task.cancel()
        if runtime.scheduler:
            runtime.scheduler.shutdown(wait=False)
        await runtime.engine.dispose()

    app = FastAPI(title=settings.app_name, docs_url="/api/docs", lifespan=lifespan)
    app.state.runtime = runtime
    static_dir = PACKAGE_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        stats = await runtime.reports.collect_stats()
        async with runtime.session_factory() as session:
            conversations = (
                await session.execute(
                    select(Conversation).order_by(Conversation.last_message_at.desc()).limit(20)
                )
            ).scalars().all()
            reports = (
                await session.execute(select(Report).order_by(Report.id.desc()).limit(5))
            ).scalars().all()
            messages = (
                await session.execute(select(Message).order_by(Message.id.desc()).limit(15))
            ).scalars().all()
        auto_reply = await runtime.pipeline.is_auto_reply_enabled()
        channels = [
            {
                "name": "telegram",
                "label": "Telegram",
                "enabled": settings.telegram_enabled,
            },
            {
                "name": "whatsapp",
                "label": "WhatsApp",
                "enabled": settings.whatsapp_enabled,
            },
            {
                "name": "instagram",
                "label": "Instagram",
                "enabled": settings.instagram_enabled,
            },
        ]
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "stats": stats,
                "conversations": conversations,
                "reports": reports,
                "messages": messages,
                "channels": channels,
                "auto_reply": auto_reply,
                "ai_enabled": runtime.ai.enabled,
                "company_name": settings.company_name,
                "channel_labels": CHANNEL_LABELS,
            },
        )

    @app.get("/conversations/{conversation_id}", response_class=HTMLResponse)
    async def conversation_page(request: Request, conversation_id: int):
        async with runtime.session_factory() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                raise HTTPException(status_code=404, detail="Диалог не найден")
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.id.asc())
                )
            ).scalars().all()
        return templates.TemplateResponse(
            request,
            "conversation.html",
            {
                "conversation": conversation,
                "messages": messages,
                "channel_labels": CHANNEL_LABELS,
            },
        )

    @app.get("/reports", response_class=HTMLResponse)
    async def reports_page(request: Request):
        async with runtime.session_factory() as session:
            reports = (
                await session.execute(select(Report).order_by(Report.id.desc()).limit(50))
            ).scalars().all()
        return templates.TemplateResponse(
            request,
            "reports.html",
            {"reports": reports},
        )

    @app.post("/actions/report")
    async def action_report():
        report = await runtime.reports.build_report(deliver=True)
        return RedirectResponse(url="/reports", status_code=303)

    @app.post("/actions/auto-reply")
    async def action_auto_reply(request: Request):
        form = await request.form()
        enabled = str(form.get("enabled", "1")) != "0"
        await runtime.pipeline.set_auto_reply(enabled)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/demo/message")
    async def demo_message(request: Request):
        form = await request.form()
        incoming = IncomingMessage(
            channel=str(form.get("channel") or "telegram"),
            chat_id=str(form.get("chat_id") or "demo-user"),
            sender_id=str(form.get("chat_id") or "demo-user"),
            sender_name=str(form.get("sender_name") or "Демо-клиент"),
            text=str(form.get("text") or "").strip(),
            message_id="demo",
            is_owner=False,
        )
        if not incoming.text:
            return RedirectResponse(url="/", status_code=303)
        await runtime.pipeline.handle(incoming)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/webhook/telegram")
    async def telegram_webhook(request: Request):
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if settings.telegram_webhook_secret and secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Bad telegram secret")
        payload = await request.json()
        incoming = parse_telegram_update(payload, settings.telegram_owner_chat_id)
        if incoming:
            await runtime.pipeline.handle(incoming)
        return {"ok": True}

    @app.get("/webhook/meta")
    @app.get("/webhook/whatsapp")
    @app.get("/webhook/instagram")
    async def meta_verify(request: Request):
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge", "")
        if mode == "subscribe" and token == settings.meta_verify_token:
            return PlainTextResponse(challenge)
        raise HTTPException(status_code=403, detail="Verification failed")

    @app.post("/webhook/meta")
    async def meta_webhook(request: Request):
        return await _handle_meta(request, runtime, settings, kind="meta")

    @app.post("/webhook/whatsapp")
    async def whatsapp_webhook(request: Request):
        return await _handle_meta(request, runtime, settings, kind="whatsapp")

    @app.post("/webhook/instagram")
    async def instagram_webhook(request: Request):
        return await _handle_meta(request, runtime, settings, kind="instagram")

    @app.get("/api/stats")
    async def api_stats():
        return await runtime.reports.collect_stats()

    @app.get("/health")
    async def health():
        return JSONResponse(
            {
                "ok": True,
                "telegram": runtime.settings.telegram_enabled,
                "whatsapp": runtime.settings.whatsapp_enabled,
                "instagram": runtime.settings.instagram_enabled,
                "ai": runtime.ai.enabled,
            }
        )

    return app


async def _handle_meta(
    request: Request, runtime: Runtime, settings: Settings, kind: str
) -> dict:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(settings.meta_app_secret, body, signature):
        raise HTTPException(status_code=403, detail="Bad Meta signature")
    payload = json.loads(body.decode("utf-8") or "{}")
    if kind == "whatsapp":
        incoming_list = parse_whatsapp_payload(
            payload,
            settings.whatsapp_owner_phone,
            settings.whatsapp_phone_number_id,
        )
    elif kind == "instagram":
        incoming_list = parse_instagram_payload(
            payload,
            settings.instagram_account_id,
            settings.instagram_owner_igsid,
        )
    else:
        incoming_list = parse_meta_payload(
            payload,
            owner_phone=settings.whatsapp_owner_phone,
            phone_number_id=settings.whatsapp_phone_number_id,
            instagram_account_id=settings.instagram_account_id,
            owner_igsid=settings.instagram_owner_igsid,
        )
    for incoming in incoming_list:
        await runtime.pipeline.handle(incoming)
    return {"ok": True}


async def _daily_report(runtime: Runtime) -> None:
    await runtime.reports.build_report(deliver=True)


async def _poll_telegram(runtime: Runtime) -> None:
    adapter = runtime.adapters.get("telegram")
    if not isinstance(adapter, TelegramAdapter):
        return
    while True:
        try:
            updates = await adapter.get_updates(offset=runtime.telegram_offset, timeout=25)
            for update in updates:
                runtime.telegram_offset = int(update.get("update_id") or 0) + 1
                incoming = parse_telegram_update(
                    update, runtime.settings.telegram_owner_chat_id
                )
                if incoming:
                    await runtime.pipeline.handle(incoming)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(3)
