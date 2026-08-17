from __future__ import annotations

from typing import Any

import httpx

from messenger_ai.adapters.base import ChannelAdapter

GRAPH_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppAdapter(ChannelAdapter):
    name = "whatsapp"
    label = "WhatsApp"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        owner_phone: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.phone_number_id = phone_number_id
        self.owner_phone = owner_phone
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.phone_number_id)

    async def send(self, chat_id: str, text: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": "text",
            "text": {"body": _plain(text)},
        }
        await self._post(f"{GRAPH_BASE}/{self.phone_number_id}/messages", payload)

    async def send_to_owner(self, text: str) -> bool:
        if not self.owner_phone:
            return False
        await self.send(self.owner_phone, text)
        return True

    async def mark_read(self, message_id: str) -> None:
        if not message_id:
            return
        await self._post(
            f"{GRAPH_BASE}/{self.phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
        )

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = await self._client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}


class InstagramAdapter(ChannelAdapter):
    name = "instagram"
    label = "Instagram"

    def __init__(
        self,
        token: str,
        account_id: str,
        owner_igsid: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.account_id = account_id
        self.owner_igsid = owner_igsid
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.account_id)

    async def send(self, chat_id: str, text: str) -> None:
        payload = {
            "recipient": {"id": chat_id},
            "message": {"text": _plain(text)},
        }
        await self._post(f"{GRAPH_BASE}/{self.account_id}/messages", payload)

    async def send_to_owner(self, text: str) -> bool:
        if not self.owner_igsid:
            return False
        await self.send(self.owner_igsid, text)
        return True

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = await self._client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}


def _plain(text: str) -> str:
    return (
        text.replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
        .replace("<code>", "")
        .replace("</code>", "")
    )
