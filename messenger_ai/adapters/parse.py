from __future__ import annotations

from typing import Any

from messenger_ai.schemas import IncomingMessage

CHANNELS = ("telegram", "whatsapp", "instagram")


def parse_telegram_update(
    payload: dict[str, Any],
    owner_chat_id: str = "",
    bot_id: str = "",
) -> IncomingMessage | None:
    message = payload.get("message") or payload.get("edited_message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from") or {}
    if sender.get("is_bot"):
        return None
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or sender.get("id") or "")
    if not chat_id:
        return None
    sender_id = str(sender.get("id") or chat_id)
    if bot_id and sender_id == str(bot_id):
        return None
    text = _extract_telegram_text(message)
    media_type = _telegram_media_type(message)
    first = sender.get("first_name") or ""
    last = sender.get("last_name") or ""
    username = sender.get("username") or ""
    name = " ".join(part for part in (first, last) if part).strip() or username or chat_id
    return IncomingMessage(
        channel="telegram",
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=name,
        text=text,
        message_id=str(message.get("message_id") or payload.get("update_id") or ""),
        is_owner=_ids_match(chat_id, owner_chat_id) or _ids_match(sender_id, owner_chat_id),
        media_type=media_type,
    )


def parse_whatsapp_payload(
    payload: dict[str, Any],
    owner_phone: str = "",
    phone_number_id: str = "",
) -> list[IncomingMessage]:
    messages: list[IncomingMessage] = []
    obj = payload.get("object")
    if obj not in (None, "whatsapp_business_account", "whatsapp"):
        return messages
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            contacts = {
                item.get("wa_id"): (item.get("profile") or {}).get("name") or ""
                for item in value.get("contacts") or []
                if item.get("wa_id")
            }
            metadata = value.get("metadata") or {}
            our_id = str(metadata.get("phone_number_id") or phone_number_id)
            for item in value.get("messages") or []:
                from_id = str(item.get("from") or "")
                if not from_id:
                    continue
                if our_id and from_id == our_id:
                    continue
                text, media_type = _whatsapp_text(item)
                messages.append(
                    IncomingMessage(
                        channel="whatsapp",
                        chat_id=from_id,
                        sender_id=from_id,
                        sender_name=contacts.get(from_id) or from_id,
                        text=text,
                        message_id=str(item.get("id") or ""),
                        is_owner=_phones_match(from_id, owner_phone),
                        media_type=media_type,
                    )
                )
    return messages


def parse_instagram_payload(
    payload: dict[str, Any],
    account_id: str = "",
    owner_igsid: str = "",
) -> list[IncomingMessage]:
    messages: list[IncomingMessage] = []
    if payload.get("object") not in (None, "instagram"):
        return messages
    for entry in payload.get("entry") or []:
        page_id = str(entry.get("id") or account_id)
        events = entry.get("messaging") or []
        if not events and entry.get("changes"):
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                if "messaging" in value:
                    events.extend(value.get("messaging") or [])
                elif value.get("sender") and (value.get("message") or value.get("text")):
                    events.append(value)
        for event in events:
            sender = (event.get("sender") or {}).get("id")
            recipient = (event.get("recipient") or {}).get("id")
            if not sender:
                continue
            sender_id = str(sender)
            if page_id and sender_id == str(page_id):
                continue
            if account_id and sender_id == str(account_id):
                continue
            if recipient and account_id and str(recipient) != str(account_id) and page_id and str(recipient) != page_id:
                # Still accept: Meta sometimes uses page id vs ig user id.
                pass
            message = event.get("message") or {}
            if message.get("is_echo"):
                continue
            text = str(message.get("text") or event.get("text") or "").strip()
            media_type = None
            if message.get("attachments"):
                media_type = str((message["attachments"][0] or {}).get("type") or "media")
            messages.append(
                IncomingMessage(
                    channel="instagram",
                    chat_id=sender_id,
                    sender_id=sender_id,
                    sender_name=sender_id,
                    text=text,
                    message_id=str(message.get("mid") or event.get("timestamp") or ""),
                    is_owner=_ids_match(sender_id, owner_igsid),
                    is_echo=bool(message.get("is_echo")),
                    media_type=media_type,
                )
            )
    return messages


def parse_meta_payload(
    payload: dict[str, Any],
    *,
    owner_phone: str = "",
    phone_number_id: str = "",
    instagram_account_id: str = "",
    owner_igsid: str = "",
) -> list[IncomingMessage]:
    obj = payload.get("object")
    if obj == "instagram":
        return parse_instagram_payload(payload, instagram_account_id, owner_igsid)
    if obj in ("whatsapp_business_account", "whatsapp"):
        return parse_whatsapp_payload(payload, owner_phone, phone_number_id)
    whatsapp = parse_whatsapp_payload(payload, owner_phone, phone_number_id)
    instagram = parse_instagram_payload(payload, instagram_account_id, owner_igsid)
    return whatsapp + instagram


def _extract_telegram_text(message: dict[str, Any]) -> str:
    if message.get("text"):
        return str(message["text"]).strip()
    if message.get("caption"):
        return str(message["caption"]).strip()
    contact = message.get("contact") or {}
    if contact.get("phone_number"):
        return f"Контакт: {contact.get('phone_number')} {contact.get('first_name') or ''}".strip()
    return ""


def _telegram_media_type(message: dict[str, Any]) -> str | None:
    for key in ("photo", "document", "video", "voice", "audio", "sticker", "video_note"):
        if message.get(key):
            return key
    return None


def _whatsapp_text(item: dict[str, Any]) -> tuple[str, str | None]:
    msg_type = str(item.get("type") or "text")
    if msg_type == "text":
        return str((item.get("text") or {}).get("body") or "").strip(), None
    if msg_type == "button":
        return str((item.get("button") or {}).get("text") or "").strip(), None
    if msg_type == "interactive":
        interactive = item.get("interactive") or {}
        button = (interactive.get("button_reply") or {}).get("title")
        lst = (interactive.get("list_reply") or {}).get("title")
        return str(button or lst or "").strip(), None
    if msg_type == "image":
        caption = str((item.get("image") or {}).get("caption") or "").strip()
        return caption, "image"
    return str(item.get("caption") or "").strip(), msg_type


def _ids_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return str(left).strip() == str(right).strip()


def _phones_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    digits = lambda value: "".join(ch for ch in value if ch.isdigit())
    a, b = digits(left), digits(right)
    if not a or not b:
        return False
    return a == b or a.endswith(b) or b.endswith(a)
