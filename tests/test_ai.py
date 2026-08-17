from messenger_ai.ai import AIClient, parse_ai_decision
from messenger_ai.schemas import IncomingMessage


def test_parse_ai_decision_json():
    decision = parse_ai_decision(
        '{"reply": "Конечно", "escalate": true, "reason": "возврат", "topic": "возврат", "sentiment": "negative"}'
    )
    assert decision.reply == "Конечно"
    assert decision.escalate is True
    assert decision.topic == "возврат"


def test_parse_ai_decision_plain_text():
    decision = parse_ai_decision("Просто текст без JSON")
    assert decision.reply == "Просто текст без JSON"
    assert decision.escalate is False


async def test_heuristic_greeting_and_escalation():
    client = AIClient(company_name="Shop")
    hi = await client.decide(
        IncomingMessage(
            channel="telegram",
            chat_id="1",
            sender_id="1",
            sender_name="A",
            text="Привет",
            message_id="1",
        ),
        [],
    )
    assert "Здравствуйте" in hi.reply
    refund = await client.decide(
        IncomingMessage(
            channel="whatsapp",
            chat_id="2",
            sender_id="2",
            sender_name="B",
            text="Хочу возврат денег, это жалоба",
            message_id="2",
        ),
        [],
    )
    assert refund.escalate is True
    media = await client.decide(
        IncomingMessage(
            channel="instagram",
            chat_id="3",
            sender_id="3",
            sender_name="C",
            text="",
            message_id="3",
            media_type="image",
        ),
        [],
    )
    assert media.escalate is True
    assert media.topic == "медиа"
