from sqlalchemy import select

from messenger_ai.models import Conversation, Message
from messenger_ai.schemas import IncomingMessage


def _msg(**kwargs) -> IncomingMessage:
    data = {
        "channel": "telegram",
        "chat_id": "42",
        "sender_id": "42",
        "sender_name": "Иван",
        "text": "Привет",
        "message_id": "m1",
    }
    data.update(kwargs)
    return IncomingMessage(**data)


async def test_auto_reply_is_stored_and_sent(runtime):
    result = await runtime.pipeline.handle(_msg())
    assert result["status"] == "replied"
    adapter = runtime.adapters["telegram"]
    assert adapter.sent
    assert adapter.sent[0][0] == "42"
    async with runtime.session_factory() as session:
        messages = (await session.execute(select(Message).order_by(Message.id))).scalars().all()
        assert [item.direction for item in messages] == ["inbound", "outbound"]
        assert messages[0].text == "Привет"
        assert messages[1].sender_name == "ИИ"


async def test_escalation_notifies_owner(runtime):
    await runtime.pipeline.handle(
        _msg(text="Хочу возврат, это жалоба директору", message_id="m2")
    )
    adapter = runtime.adapters["telegram"]
    assert adapter.owner_messages
    assert "Нужен человек" in adapter.owner_messages[-1]
    async with runtime.session_factory() as session:
        conversation = (await session.execute(select(Conversation))).scalar_one()
        assert conversation.status == "escalated"


async def test_owner_pause_and_resume(runtime):
    pause = await runtime.pipeline.handle(
        _msg(chat_id="100", sender_id="100", is_owner=True, text="/pause", message_id="o1")
    )
    assert pause["command"] == "pause"
    assert await runtime.pipeline.is_auto_reply_enabled() is False
    logged = await runtime.pipeline.handle(_msg(text="Ещё вопрос", message_id="m3", chat_id="77"))
    assert logged["status"] == "logged"
    resume = await runtime.pipeline.handle(
        _msg(chat_id="100", sender_id="100", is_owner=True, text="/resume", message_id="o2")
    )
    assert resume["command"] == "resume"
    assert await runtime.pipeline.is_auto_reply_enabled() is True


async def test_owner_report_command(runtime):
    await runtime.pipeline.handle(_msg(text="Когда доставка?", message_id="d1"))
    result = await runtime.pipeline.handle(
        _msg(chat_id="100", sender_id="100", is_owner=True, text="/report", message_id="o3")
    )
    assert result["command"] == "report"
    adapter = runtime.adapters["telegram"]
    assert any("Отчёт" in text or "Входящих" in text for _, text in adapter.sent)


async def test_whatsapp_and_instagram_channels(runtime):
    await runtime.pipeline.handle(
        _msg(channel="whatsapp", chat_id="7900", sender_id="7900", text="Цена?", message_id="w1")
    )
    await runtime.pipeline.handle(
        _msg(
            channel="instagram",
            chat_id="ig1",
            sender_id="ig1",
            text="Здравствуйте",
            message_id="i1",
        )
    )
    assert runtime.adapters["whatsapp"].sent
    assert runtime.adapters["instagram"].sent
