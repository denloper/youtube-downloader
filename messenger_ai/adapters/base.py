from __future__ import annotations

from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    name: str
    label: str

    @abstractmethod
    async def send(self, chat_id: str, text: str) -> None:
        raise NotImplementedError

    async def send_to_owner(self, text: str) -> bool:
        return False

    @property
    def enabled(self) -> bool:
        return True


class FakeAdapter(ChannelAdapter):
    def __init__(self, name: str, label: str | None = None) -> None:
        self.name = name
        self.label = label or name.title()
        self.sent: list[tuple[str, str]] = []
        self.owner_messages: list[str] = []

    async def send(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))

    async def send_to_owner(self, text: str) -> bool:
        self.owner_messages.append(text)
        return True
