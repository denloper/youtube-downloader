import json

from fastapi.testclient import TestClient

from messenger_ai.security import meta_signature_header


def test_health_and_dashboard(app):
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True
        page = client.get("/")
        assert page.status_code == 200
        assert "Messenger AI" in page.text or "ИИ-ассистент" in page.text


def test_demo_message_and_report(app, runtime):
    with TestClient(app) as client:
        response = client.post(
            "/demo/message",
            data={
                "channel": "instagram",
                "sender_name": "Катя",
                "text": "Сколько стоит доставка?",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        stats = client.get("/api/stats")
        assert stats.json()["inbound"] >= 1
        created = client.post("/actions/report", follow_redirects=False)
        assert created.status_code == 303
        reports = client.get("/reports")
        assert reports.status_code == 200
        assert "Отчёт" in reports.text


def test_telegram_webhook_and_meta_verify(app, runtime):
    with TestClient(app) as client:
        forbidden = client.post(
            "/webhook/telegram",
            json={"message": {"text": "hi"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert forbidden.status_code == 403
        ok = client.post(
            "/webhook/telegram",
            json={
                "update_id": 9,
                "message": {
                    "message_id": 3,
                    "from": {"id": 55, "first_name": "Павел"},
                    "chat": {"id": 55, "type": "private"},
                    "text": "Добрый день",
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": "messenger-ai-telegram"},
        )
        assert ok.status_code == 200
        challenge = client.get(
            "/webhook/meta",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "12345",
            },
        )
        assert challenge.status_code == 200
        assert challenge.text == "12345"


def test_whatsapp_and_instagram_webhooks(app, runtime):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"profile": {"name": "Миша"}, "wa_id": "7900123"}],
                            "messages": [
                                {
                                    "from": "7900123",
                                    "id": "w1",
                                    "type": "text",
                                    "text": {"body": "Привет"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    secret = runtime.settings.meta_app_secret
    with TestClient(app) as client:
        bad = client.post(
            "/webhook/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=nope"},
        )
        assert bad.status_code == 403
        good = client.post(
            "/webhook/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": meta_signature_header(secret, body),
            },
        )
        assert good.status_code == 200
        ig_payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "biz",
                    "messaging": [
                        {
                            "sender": {"id": "u1"},
                            "recipient": {"id": "biz"},
                            "message": {"mid": "m9", "text": "Есть в наличии?"},
                        }
                    ],
                }
            ],
        }
        ig = json.dumps(ig_payload, ensure_ascii=False).encode("utf-8")
        ig_ok = client.post(
            "/webhook/instagram",
            content=ig,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": meta_signature_header(secret, ig),
            },
        )
        assert ig_ok.status_code == 200
        assert runtime.adapters["whatsapp"].sent
        assert runtime.adapters["instagram"].sent
