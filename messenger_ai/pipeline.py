from __future__ import annotations

from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from messenger_ai.adapters.base import ChannelAdapter
from messenger_ai.ai import AIClient
from messenger_ai.models import AppSetting, Conversation, Message, utcnow
from messenger_ai.schemas import IncomingMessage

OWNER_HELP = (
    "<b>Messenger AI</b>\n\n"
    "Я читаю входящие сообщения в Telegram, WhatsApp и Instagram, "
    "отвечаю за вас и присылаю отчёты.\n\n"
    "/report — отчёт за последние 24 часа\n"
    "/stats — короткая статистика\n"
    "/pause — остановить автоответы\n"
    "/resume — включить автоответы\n"
    "/help — эта справка"
)


class Pipeline:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: dict[str, ChannelAdapter],
        ai: AIClient,
        auto_reply_default: bool = True,
        history_limit: int = 12,
        report_callback=None,
    ) -> None:
        self.session_factory = session_factory
        self.adapters = adapters
        self.ai = ai
        self.auto_reply_default = auto_reply_default
        self.history_limit = history_limit
        self.report_callback = report_callback

    async def handle(self, incoming: IncomingMessage) -> dict:
        if incoming.is_echo:
            return {"status": "ignored", "reason": "echo"}
        if incoming.is_owner:
            return await self._handle_owner(incoming)

        async with self.session_factory() as session:
            conversation = await self._upsert_conversation(session, incoming)
            await self._store_message(
                session,
                conversation,
                incoming,
                direction="inbound",
            )
            await session.commit()
            conversation_id = conversation.id
            history = await self._history(session, conversation_id)

        auto_reply = await self.is_auto_reply_enabled()
        if not auto_reply:
            await self._notify_owner(
                f"📩 <b>Новое сообщение</b> ({incoming.channel})\n"
                f"От: {escape(incoming.sender_name)}\n"
                f"{escape(incoming.text or incoming.media_type or 'без текста')}"
            )
            return {"status": "logged", "auto_reply": False}

        decision = await self.ai.decide(incoming, history)
        adapter = self.adapters.get(incoming.channel)
        sent = False
        if adapter and decision.reply:
            try:
                await adapter.send(incoming.chat_id, decision.reply)
                sent = True
            except Exception as exc:
                decision.escalate = True
                decision.reason = decision.reason or f"Не удалось отправить ответ: {exc}"
            async with self.session_factory() as session:
                conversation = await self._get_conversation(
                    session, incoming.channel, incoming.chat_id
                )
                if conversation:
                    if sent:
                        outbound = IncomingMessage(
                            channel=incoming.channel,
                            chat_id=incoming.chat_id,
                            sender_id="assistant",
                            sender_name="ИИ",
                            text=decision.reply,
                            message_id="",
                        )
                        message = await self._store_message(
                            session,
                            conversation,
                            outbound,
                            direction="outbound",
                        )
                        message.topic = decision.topic
                        message.sentiment = decision.sentiment
                        message.escalated = decision.escalate
                    inbound = (
                        await session.execute(
                            select(Message)
                            .where(
                                Message.conversation_id == conversation.id,
                                Message.direction == "inbound",
                            )
                            .order_by(Message.id.desc())
                        )
                    ).scalars().first()
                    if inbound:
                        inbound.topic = decision.topic
                        inbound.sentiment = decision.sentiment
                        inbound.escalated = decision.escalate
                    if decision.escalate:
                        conversation.status = "escalated"
                    await session.commit()

        if decision.escalate:
            reason = escape(decision.reason or "нужна ручная обработка")
            await self._notify_owner(
                "⚠️ <b>Нужен человек</b>\n"
                f"Канал: {incoming.channel}\n"
                f"От: {escape(incoming.sender_name)}\n"
                f"Сообщение: {escape(incoming.text or incoming.media_type or '')}\n"
                f"Причина: {reason}"
            )
        return {
            "status": "replied" if sent else "processed",
            "escalate": decision.escalate,
            "topic": decision.topic,
            "reply": decision.reply if sent else "",
        }

    async def is_auto_reply_enabled(self) -> bool:
        async with self.session_factory() as session:
            row = await session.get(AppSetting, "auto_reply")
            if row is None:
                return self.auto_reply_default
            return row.value != "0"

    async def set_auto_reply(self, enabled: bool) -> None:
        async with self.session_factory() as session:
            row = await session.get(AppSetting, "auto_reply")
            if row is None:
                session.add(AppSetting(key="auto_reply", value="1" if enabled else "0"))
            else:
                row.value = "1" if enabled else "0"
            await session.commit()

    async def _handle_owner(self, incoming: IncomingMessage) -> dict:
        command = (incoming.text or "").strip().split()
        name = command[0].lower() if command else ""
        if name.startswith("/start") or name.startswith("/help"):
            await self._reply_owner(incoming, OWNER_HELP)
            return {"status": "owner", "command": "help"}
        if name.startswith("/pause"):
            await self.set_auto_reply(False)
            await self._reply_owner(incoming, "Автоответы выключены. Сообщения будут только сохраняться.")
            return {"status": "owner", "command": "pause"}
        if name.startswith("/resume"):
            await self.set_auto_reply(True)
            await self._reply_owner(incoming, "Автоответы включены.")
            return {"status": "owner", "command": "resume"}
        if name.startswith("/stats"):
            if self.report_callback:
                text = await self.report_callback(kind="stats")
            else:
                text = "Статистика пока недоступна."
            await self._reply_owner(incoming, text)
            return {"status": "owner", "command": "stats"}
        if name.startswith("/report"):
            if self.report_callback:
                text = await self.report_callback(kind="report")
            else:
                text = "Отчёт пока недоступен."
            await self._reply_owner(incoming, text)
            return {"status": "owner", "command": "report"}
        await self._reply_owner(
            incoming,
            "Команда не распознана. Напишите /help — или это сообщение не будет отправлено клиентам.",
        )
        return {"status": "owner", "command": "unknown"}

    async def _reply_owner(self, incoming: IncomingMessage, text: str) -> None:
        adapter = self.adapters.get(incoming.channel)
        if adapter:
            await adapter.send(incoming.chat_id, text)

    async def _notify_owner(self, text: str) -> None:
        telegram = self.adapters.get("telegram")
        if telegram and await telegram.send_to_owner(text):
            return
        for adapter in self.adapters.values():
            if await adapter.send_to_owner(text):
                return

    async def _upsert_conversation(
        self, session: AsyncSession, incoming: IncomingMessage
    ) -> Conversation:
        result = await session.execute(
            select(Conversation).where(
                Conversation.channel == incoming.channel,
                Conversation.chat_id == incoming.chat_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            conversation = Conversation(
                channel=incoming.channel,
                chat_id=incoming.chat_id,
                sender_name=incoming.sender_name,
                status="active",
                last_message_at=utcnow(),
            )
            session.add(conversation)
            await session.flush()
            return conversation
        conversation.sender_name = incoming.sender_name or conversation.sender_name
        conversation.last_message_at = utcnow()
        if conversation.status == "closed":
            conversation.status = "active"
        return conversation

    async def _get_conversation(
        self, session: AsyncSession, channel: str, chat_id: str
    ) -> Conversation | None:
        result = await session.execute(
            select(Conversation).where(
                Conversation.channel == channel,
                Conversation.chat_id == chat_id,
            )
        )
        return result.scalar_one_or_none()

    async def _store_message(
        self,
        session: AsyncSession,
        conversation: Conversation,
        incoming: IncomingMessage,
        direction: str,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            channel=incoming.channel,
            chat_id=incoming.chat_id,
            direction=direction,
            sender_id=incoming.sender_id,
            sender_name=incoming.sender_name,
            external_id=incoming.message_id,
            text=incoming.text,
        )
        session.add(message)
        await session.flush()
        return message

    async def _history(self, session: AsyncSession, conversation_id: int) -> list[dict[str, str]]:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(self.history_limit)
        )
        rows = list(reversed(result.scalars().all()))
        history: list[dict[str, str]] = []
        for row in rows:
            if not row.text:
                continue
            role = "assistant" if row.direction == "outbound" else "user"
            history.append({"role": role, "content": row.text})
        return history
