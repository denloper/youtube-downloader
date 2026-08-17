from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IncomingMessage:
    channel: str
    chat_id: str
    sender_id: str
    sender_name: str
    text: str
    message_id: str
    is_owner: bool = False
    is_echo: bool = False
    media_type: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AIDecision:
    reply: str
    escalate: bool = False
    reason: str | None = None
    topic: str = "общее"
    sentiment: str = "neutral"


@dataclass
class ChannelStatus:
    name: str
    enabled: bool
    label: str
