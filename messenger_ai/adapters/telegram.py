from __future__ import annotations

from typing import Any

import httpx

from messenger_ai.adapters.base import ChannelAdapter


class TelegramAdapter(ChannelAdapter):
    name = "telegram"
    label = "Telegram"

    def __init__(
        self,
        token: str,
        owner_chat_id: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.owner_chat_id = owner_chat_id
        self._client = client
        self._base = f"https://api.telegram.org/bot{token}"

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def send(self, chat_id: str, text: str) -> None:
        await self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
        )

    async def send_to_owner(self, text: str) -> bool:
        if not self.owner_chat_id:
            return False
        await self.send(self.owner_chat_id, text)
        return True

    async def get_updates(self, offset: int = 0, timeout: int = 25) -> list[dict[str, Any]]:
        data = await self._call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
        )
        return list(data.get("result") or [])

    async def set_webhook(self, url: str, secret: str) -> None:
        await self._call(
            "setWebhook",
            {"url": url, "secret_token": secret, "allowed_updates": ["message"]},
        )

    async def delete_webhook(self) -> None:
        await self._call("deleteWebhook", {})

    async def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/{method}"
        if self._client is not None:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
