# Messenger AI

ИИ читает входящие сообщения в **Telegram**, **WhatsApp** и **Instagram**, отвечает клиентам и присылает вам отчёт.

Работает только через официальные API: Telegram Bot API, WhatsApp Cloud API и Instagram Messaging API. Неофициальный вход в чужие аккаунты и WhatsApp Web не используется.

## Что умеет

- Принимает сообщения из трёх каналов
- Отвечает автоматически (OpenAI или совместимый API; без ключа — аккуратный демо-режим)
- Передаёт сложные случаи вам: возврат, жалоба, вложение без текста
- Пишет отчёт за 24 часа: сколько сообщений, по каким каналам, какие темы, что требует внимания
- Отправляет отчёт владельцу в Telegram каждый день и по команде `/report`
- Показывает переписки и отчёты в веб-панели

## Быстрый старт

Нужен Python 3.10+.

```bash
cp .env.example .env
pip install -r requirements-ai.txt
python -m messenger_ai
```

Откройте http://127.0.0.1:8080

На панели можно сразу отправить демо-сообщение — ИИ ответит, диалог сохранится, кнопка «Сформировать отчёт» покажет сводку.

Windows: `start-messenger.bat`

## Команды владельца в Telegram

Напишите своему боту:

- `/report` — отчёт за последние 24 часа
- `/stats` — короткая статистика
- `/pause` — остановить автоответы (сообщения только копятся)
- `/resume` — снова отвечать
- `/help` — справка

Чтобы отчёты приходили вам, укажите `TELEGRAM_BOT_TOKEN` и `TELEGRAM_OWNER_CHAT_ID`. Свой chat id можно узнать у `@userinfobot`.

## Подключение каналов

### 1. Telegram

1. Создайте бота в [@BotFather](https://t.me/BotFather) и скопируйте токен в `TELEGRAM_BOT_TOKEN`.
2. Напишите боту `/start`.
3. Укажите свой chat id в `TELEGRAM_OWNER_CHAT_ID`.
4. Если `PUBLIC_BASE_URL` пустой, бот сам читает сообщения (long polling). Если задан HTTPS-адрес, ставится вебхук `/webhook/telegram`.

### 2. WhatsApp Cloud API

1. В [Meta for Developers](https://developers.facebook.com/) создайте приложение с продуктом WhatsApp.
2. Возьмите постоянный токен и Phone number ID.
3. Вебхук: `https://ваш-домен/webhook/whatsapp`
4. Verify token — тот же, что `META_VERIFY_TOKEN`.
5. Подпишитесь на поле `messages`.
6. Заполните `WHATSAPP_TOKEN` и `WHATSAPP_PHONE_NUMBER_ID`.

Отвечать можно только пользователям, которые сами написали вам (окно 24 часа).

### 3. Instagram

Нужен профессиональный аккаунт Instagram, привязанный к странице Facebook.

1. В том же приложении Meta включите Instagram Messaging.
2. Вебхук: `https://ваш-домен/webhook/instagram` или общий `/webhook/meta`.
3. Подпишитесь на сообщения Instagram.
4. Заполните `INSTAGRAM_ACCESS_TOKEN` и `INSTAGRAM_ACCOUNT_ID` (IG user id).

Для проверки вебхуков Meta нужен публичный HTTPS. Удобно: [ngrok](https://ngrok.com/) или Cloudflare Tunnel. Пропишите его в `PUBLIC_BASE_URL`.

## ИИ

По умолчанию используется Chat Completions (`OPENAI_BASE_URL` + `OPENAI_API_KEY` + `OPENAI_MODEL`). Подойдёт OpenAI, Groq, OpenRouter или локальный сервер с тем же протоколом.

Если ключа нет, ассистент всё равно отвечает по простым правилам и собирает отчёты по фактам из переписок.

## Отчёты

Ежедневно в `REPORT_HOUR` (по умолчанию 20:00, `Europe/Moscow`) отчёт уходит владельцу в Telegram и сохраняется на странице `/reports`.

В отчёте:

- число входящих и ответов ИИ
- разбивка по Telegram / WhatsApp / Instagram
- темы и настроение
- сообщения, которые нужно обработать вручную
- краткий разбор, если подключён ИИ

## Тесты

```bash
pip install -r requirements-ai.txt
pytest -q
```
