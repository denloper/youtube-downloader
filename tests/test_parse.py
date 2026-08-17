from messenger_ai.adapters.parse import (
    parse_instagram_payload,
    parse_meta_payload,
    parse_telegram_update,
    parse_whatsapp_payload,
)


def test_parse_telegram_text():
    incoming = parse_telegram_update(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 42, "first_name": "Иван"},
                "chat": {"id": 42, "type": "private"},
                "text": "Привет",
            },
        },
        owner_chat_id="100",
    )
    assert incoming is not None
    assert incoming.channel == "telegram"
    assert incoming.text == "Привет"
    assert incoming.sender_name == "Иван"
    assert incoming.is_owner is False


def test_parse_telegram_owner_and_skip_bot():
    owner = parse_telegram_update(
        {
            "message": {
                "message_id": 1,
                "from": {"id": 100, "first_name": "Owner"},
                "chat": {"id": 100},
                "text": "/report",
            }
        },
        owner_chat_id="100",
    )
    assert owner is not None
    assert owner.is_owner is True

    bot = parse_telegram_update(
        {
            "message": {
                "message_id": 2,
                "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                "chat": {"id": 1},
                "text": "ignore",
            }
        }
    )
    assert bot is None


def test_parse_whatsapp_text_and_ignore_status_only():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "pnid"},
                            "contacts": [{"profile": {"name": "Мария"}, "wa_id": "79001112233"}],
                            "messages": [
                                {
                                    "from": "79001112233",
                                    "id": "wamid.1",
                                    "type": "text",
                                    "text": {"body": "Где заказ?"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }
    messages = parse_whatsapp_payload(payload, owner_phone="79000000000")
    assert len(messages) == 1
    assert messages[0].sender_name == "Мария"
    assert messages[0].text == "Где заказ?"
    assert messages[0].is_owner is False

    statuses = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.1", "status": "read"}]}}]}],
    }
    assert parse_whatsapp_payload(statuses) == []


def test_parse_instagram_and_skip_echo():
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "ig-business",
                "messaging": [
                    {
                        "sender": {"id": "user-1"},
                        "recipient": {"id": "ig-business"},
                        "message": {"mid": "m1", "text": "Есть размер M?"},
                    },
                    {
                        "sender": {"id": "ig-business"},
                        "recipient": {"id": "user-1"},
                        "message": {"mid": "m2", "text": "echo", "is_echo": True},
                    },
                ],
            }
        ],
    }
    messages = parse_instagram_payload(payload, account_id="ig-business")
    assert len(messages) == 1
    assert messages[0].text == "Есть размер M?"
    assert messages[0].chat_id == "user-1"


def test_parse_meta_routes_by_object():
    instagram = parse_meta_payload(
        {"object": "instagram", "entry": []},
        instagram_account_id="ig",
    )
    assert instagram == []
    whatsapp = parse_meta_payload(
        {"object": "whatsapp_business_account", "entry": []},
        phone_number_id="pn",
    )
    assert whatsapp == []
