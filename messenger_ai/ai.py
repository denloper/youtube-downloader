from __future__ import annotations

import json
import re
from typing import Any

import httpx

from messenger_ai.schemas import AIDecision, IncomingMessage

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

FALLBACK_REPLY = (
    "Спасибо за сообщение! Я получил его и скоро отвечу подробнее. "
    "Если вопрос срочный, напишите, пожалуйста, чуть конкретнее."
)

MEDIA_REPLY = (
    "Спасибо! Сейчас я уверенно читаю только текстовые сообщения. "
    "Напишите, пожалуйста, вопрос словами — или я передам это человеку."
)


class AIClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        system_prompt: str = "",
        company_name: str = "Компания",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.company_name = company_name
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def decide(
        self,
        incoming: IncomingMessage,
        history: list[dict[str, str]],
    ) -> AIDecision:
        if incoming.media_type and not incoming.text.strip():
            return AIDecision(
                reply=MEDIA_REPLY,
                escalate=True,
                reason="Вложение без текста",
                topic="медиа",
                sentiment="neutral",
            )
        if not incoming.text.strip():
            return AIDecision(
                reply=FALLBACK_REPLY,
                escalate=False,
                topic="пустое",
                sentiment="neutral",
            )
        if not self.enabled:
            return self._heuristic(incoming)
        try:
            return await self._complete(incoming, history)
        except Exception:
            heuristic = self._heuristic(incoming)
            heuristic.escalate = True
            heuristic.reason = "Ошибка ИИ, нужен человек"
            return heuristic

    async def summarize_report(self, stats_text: str) -> str:
        if not self.enabled:
            return ""
        try:
            payload = {
                "model": self.model,
                "temperature": 0.3,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Ты аналитик службы поддержки. По статистике переписок "
                            "напиши короткий отчёт на русском: 4–7 предложений, "
                            "что происходило, какие темы, на что обратить внимание."
                        ),
                    },
                    {"role": "user", "content": stats_text},
                ],
            }
            data = await self._post_chat(payload)
            return str(data["choices"][0]["message"]["content"]).strip()
        except Exception:
            return ""

    async def _complete(
        self,
        incoming: IncomingMessage,
        history: list[dict[str, str]],
    ) -> AIDecision:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_message()},
            *history,
            {
                "role": "user",
                "content": f"Канал: {incoming.channel}\nИмя: {incoming.sender_name}\nСообщение: {incoming.text}",
            },
        ]
        payload = {
            "model": self.model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        try:
            data = await self._post_chat(payload)
        except Exception:
            payload.pop("response_format", None)
            data = await self._post_chat(payload)
        content = str(data["choices"][0]["message"]["content"])
        return parse_ai_decision(content)

    async def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        if self._client is not None:
            response = await self._client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def _system_message(self) -> str:
        return (
            f"Компания: {self.company_name}.\n"
            f"{self.system_prompt}\n\n"
            "Верни строго JSON с полями:\n"
            '{"reply": "текст ответа клиенту", "escalate": false, '
            '"reason": null, "topic": "короткая тема", '
            '"sentiment": "positive|neutral|negative"}'
        )

    def _heuristic(self, incoming: IncomingMessage) -> AIDecision:
        text = incoming.text.lower()
        escalate_words = (
            "возврат",
            "жалоб",
            "юрист",
            "суд",
            "мошен",
            "полиц",
            "не работает",
            "срочно",
            "директор",
        )
        if any(word in text for word in escalate_words):
            return AIDecision(
                reply=(
                    "Спасибо, что написали. Этот вопрос лучше передать специалисту — "
                    "я уже отправил уведомление, с вами свяжутся."
                ),
                escalate=True,
                reason="Ключевые слова, нужна ручная обработка",
                topic="эскалация",
                sentiment="negative" if any(w in text for w in ("жалоб", "мошен")) else "neutral",
            )
        if any(word in text for word in ("цена", "стоимость", "сколько стоит")):
            return AIDecision(
                reply="Подскажите, пожалуйста, какой товар или услуга вас интересует — уточню стоимость.",
                topic="цены",
            )
        if any(word in text for word in ("доставк", "когда придет", "трек")):
            return AIDecision(
                reply="Напишите, пожалуйста, номер заказа — проверю информацию по доставке.",
                topic="доставка",
            )
        if any(word in text for word in ("привет", "здравств", "добрый", "hello", "hi")):
            return AIDecision(
                reply=f"Здравствуйте! Это ассистент «{self.company_name}». Чем могу помочь?",
                topic="приветствие",
                sentiment="positive",
            )
        return AIDecision(reply=FALLBACK_REPLY, topic="общее")


def parse_ai_decision(content: str) -> AIDecision:
    raw = content.strip()
    match = JSON_RE.search(raw)
    if not match:
        return AIDecision(reply=raw or FALLBACK_REPLY)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return AIDecision(reply=raw or FALLBACK_REPLY)
    reply = str(data.get("reply") or data.get("message") or "").strip() or FALLBACK_REPLY
    reason = data.get("reason")
    return AIDecision(
        reply=reply,
        escalate=bool(data.get("escalate")),
        reason=str(reason) if reason else None,
        topic=str(data.get("topic") or "общее")[:120],
        sentiment=str(data.get("sentiment") or "neutral")[:32],
    )
