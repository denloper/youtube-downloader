# YouTube Downloader и Messenger AI

В этом репозитории два независимых инструмента.

## YouTube Downloader

Десктопная программа для скачивания видео и аудио с YouTube по ссылке.

- Форматы: **MP4** и **MP3**
- Выбор разрешения для видео и качества для аудио
- Папка сохранения на выбор
- Готовый `.exe` — Python ставить не нужно

### Скачать программу

Готовый файл: [Releases](../../releases/latest) → `YouTubeDownloader.exe`

1. Вставьте ссылку на видео YouTube
2. Нажмите **Получить информацию**
3. Выберите **MP4** или **MP3** и качество
4. Нажмите **Скачать**

По умолчанию файлы сохраняются в папку «Загрузки».

### Запуск из исходников

Нужен Python 3.10+.

```bat
pip install -r requirements.txt
python app.py
```

### Сборка exe

Запустите `build.bat` — готовый файл появится в `dist\YouTubeDownloader.exe`.

## Messenger AI

ИИ читает сообщения в Telegram, WhatsApp и Instagram, отвечает клиентам и присылает вам отчёт.

Подробная инструкция: [messenger_ai/README.md](messenger_ai/README.md)

```bash
cp .env.example .env
pip install -r requirements-ai.txt
python -m messenger_ai
```

Панель: http://127.0.0.1:8080
