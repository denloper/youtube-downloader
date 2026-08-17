from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from messenger_ai.adapters.base import ChannelAdapter
from messenger_ai.ai import AIClient
from messenger_ai.models import Conversation, Message, Report, utcnow

CHANNEL_LABELS = {
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
}


class ReportService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: dict[str, ChannelAdapter],
        ai: AIClient,
        timezone_name: str = "Europe/Moscow",
    ) -> None:
        self.session_factory = session_factory
        self.adapters = adapters
        self.ai = ai
        self.timezone_name = timezone_name

    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone_name)
        except Exception:
            return ZoneInfo("UTC")

    async def collect_stats(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> dict:
        end = period_end or utcnow()
        start = period_start or (end - timedelta(hours=24))
        async with self.session_factory() as session:
            inbound = (
                await session.execute(
                    select(Message).where(
                        Message.direction == "inbound",
                        Message.created_at >= start,
                        Message.created_at <= end,
                    )
                )
            ).scalars().all()
            outbound = (
                await session.execute(
                    select(func.count(Message.id)).where(
                        Message.direction == "outbound",
                        Message.created_at >= start,
                        Message.created_at <= end,
                    )
                )
            ).scalar_one()
            conversations = (
                await session.execute(
                    select(func.count(Conversation.id)).where(
                        Conversation.last_message_at >= start
                    )
                )
            ).scalar_one()
            escalated = [item for item in inbound if item.escalated]
            by_channel = Counter(item.channel for item in inbound)
            topics = Counter(item.topic or "общее" for item in inbound if item.topic)
            sentiments = Counter(item.sentiment or "neutral" for item in inbound)
            samples = []
            for item in inbound[:8]:
                samples.append(
                    {
                        "channel": item.channel,
                        "from": item.sender_name,
                        "text": (item.text or "")[:280],
                    }
                )
            needs_attention = [
                {
                    "channel": item.channel,
                    "from": item.sender_name,
                    "text": (item.text or "")[:280],
                    "reason": "эскалация",
                }
                for item in escalated[:10]
            ]
        return {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "inbound": len(inbound),
            "outbound": int(outbound or 0),
            "conversations": int(conversations or 0),
            "escalated": len(escalated),
            "by_channel": dict(by_channel),
            "topics": dict(topics.most_common(8)),
            "sentiments": dict(sentiments),
            "samples": samples,
            "needs_attention": needs_attention,
        }

    async def build_report(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        deliver: bool = True,
    ) -> Report:
        end = period_end or utcnow()
        start = period_start or (end - timedelta(hours=24))
        stats = await self.collect_stats(start, end)
        narrative = await self.ai.summarize_report(self._stats_plain(stats))
        title = self._title(start, end)
        body_html = self._render_html(title, stats, narrative)
        body_text = self._render_text(title, stats, narrative)
        async with self.session_factory() as session:
            report = Report(
                period_start=start,
                period_end=end,
                title=title,
                body_html=body_html,
                body_text=body_text,
                stats_json=json.dumps(stats, ensure_ascii=False),
                delivered=False,
            )
            session.add(report)
            await session.commit()
            await session.refresh(report)
            report_id = report.id
        delivered = False
        if deliver:
            delivered = await self.deliver(body_html)
            async with self.session_factory() as session:
                stored = await session.get(Report, report_id)
                if stored:
                    stored.delivered = delivered
                    await session.commit()
                    stored.body_html = body_html
                    stored.body_text = body_text
                    stored.title = title
                    return stored
        async with self.session_factory() as session:
            stored = await session.get(Report, report_id)
            assert stored is not None
            return stored

    async def short_stats(self) -> str:
        stats = await self.collect_stats()
        lines = ["<b>Статистика за 24 часа</b>"]
        if not stats["inbound"]:
            lines.append("Входящих сообщений пока нет.")
            return "\n".join(lines)
        lines.append(f"Входящих: {stats['inbound']}")
        lines.append(f"Ответов ИИ: {stats['outbound']}")
        lines.append(f"Диалогов: {stats['conversations']}")
        lines.append(f"Эскалаций: {stats['escalated']}")
        for channel, count in stats["by_channel"].items():
            lines.append(f"• {CHANNEL_LABELS.get(channel, channel)}: {count}")
        return "\n".join(lines)

    async def deliver(self, html: str) -> bool:
        telegram = self.adapters.get("telegram")
        if telegram and await telegram.send_to_owner(html):
            return True
        for adapter in self.adapters.values():
            if await adapter.send_to_owner(_strip_html(html)):
                return True
        return False

    def _title(self, start: datetime, end: datetime) -> str:
        local = self.tz()
        return (
            f"Отчёт {start.astimezone(local):%d.%m.%Y %H:%M}"
            f" — {end.astimezone(local):%d.%m.%Y %H:%M}"
        )

    def _stats_plain(self, stats: dict) -> str:
        lines = [
            f"Входящих: {stats['inbound']}",
            f"Ответов: {stats['outbound']}",
            f"Диалогов: {stats['conversations']}",
            f"Эскалаций: {stats['escalated']}",
            f"Каналы: {stats['by_channel']}",
            f"Темы: {stats['topics']}",
            f"Настроение: {stats['sentiments']}",
        ]
        for item in stats["needs_attention"]:
            lines.append(f"Внимание: {item['from']} ({item['channel']}): {item['text']}")
        return "\n".join(lines)

    def _render_html(self, title: str, stats: dict, narrative: str) -> str:
        parts = [f"<b>{escape(title)}</b>", ""]
        if not stats["inbound"]:
            parts.append("За период входящих сообщений не было.")
            return "\n".join(parts)
        parts.append(
            f"Входящих: <b>{stats['inbound']}</b> · ответов ИИ: <b>{stats['outbound']}</b> · "
            f"диалогов: <b>{stats['conversations']}</b>"
        )
        parts.append(f"Передано человеку: <b>{stats['escalated']}</b>")
        parts.append("")
        parts.append("<b>По каналам</b>")
        for channel, count in stats["by_channel"].items():
            parts.append(f"• {CHANNEL_LABELS.get(channel, channel)}: {count}")
        if stats["topics"]:
            parts.append("")
            parts.append("<b>Темы</b>")
            for topic, count in stats["topics"].items():
                parts.append(f"• {escape(str(topic))}: {count}")
        if stats["needs_attention"]:
            parts.append("")
            parts.append("<b>Нужно внимание</b>")
            for item in stats["needs_attention"]:
                parts.append(
                    f"• {CHANNEL_LABELS.get(item['channel'], item['channel'])} / "
                    f"{escape(item['from'])}: {escape(item['text'])}"
                )
        if narrative:
            parts.append("")
            parts.append("<b>Краткий разбор</b>")
            parts.append(escape(narrative))
        return "\n".join(parts)

    def _render_text(self, title: str, stats: dict, narrative: str) -> str:
        return _strip_html(self._render_html(title, stats, narrative))


def _strip_html(value: str) -> str:
    return (
        value.replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
        .replace("<code>", "")
        .replace("</code>", "")
    )
