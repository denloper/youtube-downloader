import os
import re
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import imageio_ffmpeg
import yt_dlp

APP_TITLE = "YouTube Downloader"
WINDOW_SIZE = "720x780"
YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+",
    re.IGNORECASE,
)
COMMON_HEIGHTS = (2160, 1440, 1080, 720, 480, 360, 240)


def resource_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_download_dir() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.exists() else resource_base()


def ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.search(url.strip()))


def format_duration(seconds) -> str:
    if seconds is None:
        return "неизвестно"
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "неизвестно"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(num_bytes) -> str:
    if not num_bytes:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class YouTubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(680, 740)
        self.configure(fg_color="#101218")

        self.video_info = None
        self.available_heights = []
        self.is_busy = False
        self.download_dir = default_download_dir()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color="#2a2f3a",
        )
        container.pack(fill="both", expand=True, padx=22, pady=18)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 18))

        ctk.CTkLabel(
            header,
            text="YouTube Downloader",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Скачайте видео или аудио по ссылке — выберите формат и качество",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
        ).pack(anchor="w", pady=(4, 0))

        url_card = self._card(container)
        ctk.CTkLabel(
            url_card,
            text="Ссылка на видео",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#e2e8f0",
        ).pack(anchor="w")

        url_row = ctk.CTkFrame(url_card, fg_color="transparent")
        url_row.pack(fill="x", pady=(10, 10))

        self.url_entry = ctk.CTkEntry(
            url_row,
            height=42,
            placeholder_text="https://www.youtube.com/watch?v=...",
            font=ctk.CTkFont(size=13),
            fg_color="#1b1f2a",
            border_color="#2d3340",
        )
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.url_entry.bind("<Return>", lambda _e: self.fetch_info())

        ctk.CTkButton(
            url_row,
            text="Вставить",
            width=100,
            height=42,
            fg_color="#2a3140",
            hover_color="#3a4254",
            command=self.paste_url,
        ).pack(side="left", padx=(8, 0))

        self.fetch_button = ctk.CTkButton(
            url_card,
            text="Получить информацию",
            height=40,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self.fetch_info,
        )
        self.fetch_button.pack(fill="x")

        info_card = self._card(container)
        ctk.CTkLabel(
            info_card,
            text="Информация о видео",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#e2e8f0",
        ).pack(anchor="w")

        self.title_label = self._info_row(info_card, "Название")
        self.channel_label = self._info_row(info_card, "Канал")
        self.duration_label = self._info_row(info_card, "Длительность")

        options_card = self._card(container)
        ctk.CTkLabel(
            options_card,
            text="Параметры скачивания",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#e2e8f0",
        ).pack(anchor="w")

        ctk.CTkLabel(
            options_card,
            text="Формат",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        ).pack(anchor="w", pady=(12, 6))

        self.format_var = ctk.StringVar(value="mp4")
        format_row = ctk.CTkFrame(options_card, fg_color="transparent")
        format_row.pack(fill="x")

        self.mp4_button = ctk.CTkSegmentedButton(
            format_row,
            values=["MP4", "MP3"],
            command=self._on_format_change,
            selected_color="#2563eb",
            selected_hover_color="#1d4ed8",
            unselected_color="#1b1f2a",
            unselected_hover_color="#252a36",
            height=38,
        )
        self.mp4_button.set("MP4")
        self.mp4_button.pack(fill="x")

        ctk.CTkLabel(
            options_card,
            text="Разрешение / качество",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        ).pack(anchor="w", pady=(14, 6))

        self.quality_menu = ctk.CTkOptionMenu(
            options_card,
            values=["Сначала получите информацию о видео"],
            height=38,
            fg_color="#1b1f2a",
            button_color="#2563eb",
            button_hover_color="#1d4ed8",
            dropdown_fg_color="#1b1f2a",
        )
        self.quality_menu.set("Сначала получите информацию о видео")
        self.quality_menu.pack(fill="x")

        ctk.CTkLabel(
            options_card,
            text="Папка сохранения",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        ).pack(anchor="w", pady=(14, 6))

        folder_row = ctk.CTkFrame(options_card, fg_color="transparent")
        folder_row.pack(fill="x")

        self.folder_entry = ctk.CTkEntry(
            folder_row,
            height=38,
            fg_color="#1b1f2a",
            border_color="#2d3340",
        )
        self.folder_entry.insert(0, str(self.download_dir))
        self.folder_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            folder_row,
            text="Обзор",
            width=90,
            height=38,
            fg_color="#2a3140",
            hover_color="#3a4254",
            command=self.choose_folder,
        ).pack(side="left", padx=(8, 0))

        progress_card = self._card(container)
        self.status_label = ctk.CTkLabel(
            progress_card,
            text="Вставьте ссылку и нажмите «Получить информацию»",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
            wraplength=620,
            justify="left",
        )
        self.status_label.pack(anchor="w")

        self.progress = ctk.CTkProgressBar(
            progress_card,
            height=12,
            progress_color="#2563eb",
            fg_color="#1b1f2a",
        )
        self.progress.pack(fill="x", pady=(12, 0))
        self.progress.set(0)

        self.download_button = ctk.CTkButton(
            container,
            text="Скачать",
            height=48,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self.start_download,
        )
        self.download_button.pack(fill="x", pady=(8, 16))

    def _card(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color="#161a22",
            border_color="#262b36",
            border_width=1,
            corner_radius=14,
        )
        card.pack(fill="x", pady=(0, 14))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=16)
        return inner

    def _info_row(self, parent, title: str):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(
            wrap,
            text=title,
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        ).pack(anchor="w")
        value = ctk.CTkLabel(
            wrap,
            text="—",
            font=ctk.CTkFont(size=14),
            text_color="#f1f5f9",
            wraplength=620,
            justify="left",
        )
        value.pack(anchor="w")
        return value

    def paste_url(self):
        try:
            text = self.clipboard_get().strip()
        except Exception:
            return
        if text:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, text)

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if folder:
            self.download_dir = Path(folder)
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder)

    def _on_format_change(self, value: str):
        self.format_var.set(value.lower())
        self._refresh_quality_options()

    def _set_busy(self, busy: bool):
        self.is_busy = busy
        state = "disabled" if busy else "normal"
        self.fetch_button.configure(state=state)
        self.download_button.configure(state=state)
        self.mp4_button.configure(state=state)
        self.quality_menu.configure(state=state)

    def _set_status(self, text: str):
        self.status_label.configure(text=text)

    def fetch_info(self):
        if self.is_busy:
            return
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Вставьте ссылку на видео YouTube.")
            return
        if not is_youtube_url(url):
            messagebox.showwarning(APP_TITLE, "Похоже, это не ссылка на YouTube.")
            return

        self._set_busy(True)
        self._set_status("Получаю информацию о видео...")
        self.progress.set(0)
        threading.Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def _fetch_info_worker(self, url: str):
        try:
            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "ffmpeg_location": ffmpeg_path(),
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                entries = info.get("entries") or []
                if not entries:
                    raise RuntimeError("Плейлист пуст или недоступен.")
                info = entries[0]
            self.after(0, lambda: self._apply_video_info(info))
        except Exception as exc:
            self.after(0, lambda: self._fetch_failed(str(exc)))

    def _apply_video_info(self, info: dict):
        self.video_info = info
        self.available_heights = self._collect_heights(info)
        self.title_label.configure(text=info.get("title") or "Без названия")
        self.channel_label.configure(text=info.get("uploader") or info.get("channel") or "—")
        self.duration_label.configure(text=format_duration(info.get("duration")))
        self._refresh_quality_options()
        self._set_status("Информация получена. Выберите формат и нажмите «Скачать».")
        self._set_busy(False)

    def _fetch_failed(self, error: str):
        self.video_info = None
        self._set_status("Не удалось получить информацию о видео.")
        self._set_busy(False)
        messagebox.showerror(APP_TITLE, f"Ошибка при получении информации:\n{error}")

    def _collect_heights(self, info: dict) -> list[int]:
        heights = set()
        for item in info.get("formats") or []:
            if item.get("vcodec") in (None, "none"):
                continue
            height = item.get("height")
            if height:
                heights.add(int(height))
        if not heights:
            heights.update(COMMON_HEIGHTS)
        return sorted(heights, reverse=True)

    def _refresh_quality_options(self):
        if self.format_var.get() == "mp3":
            values = ["192 kbps (рекомендуется)", "320 kbps", "128 kbps"]
            self.quality_menu.configure(values=values)
            self.quality_menu.set(values[0])
            return

        if not self.available_heights:
            values = ["Сначала получите информацию о видео"]
            self.quality_menu.configure(values=values)
            self.quality_menu.set(values[0])
            return

        values = [f"{height}p" for height in self.available_heights]
        if values:
            values.insert(0, f"Лучшее ({values[0]})")
        self.quality_menu.configure(values=values)
        self.quality_menu.set(values[0])

    def _selected_height(self) -> int | None:
        raw = self.quality_menu.get()
        match = re.search(r"(\d+)p", raw)
        if match:
            return int(match.group(1))
        return self.available_heights[0] if self.available_heights else None

    def _selected_audio_quality(self) -> str:
        raw = self.quality_menu.get()
        match = re.search(r"(\d+)", raw)
        return match.group(1) if match else "192"

    def start_download(self):
        if self.is_busy:
            return
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Вставьте ссылку на видео YouTube.")
            return
        if not is_youtube_url(url):
            messagebox.showwarning(APP_TITLE, "Похоже, это не ссылка на YouTube.")
            return
        if not self.video_info:
            messagebox.showinfo(APP_TITLE, "Сначала получите информацию о видео.")
            return

        folder = Path(self.folder_entry.get().strip() or self.download_dir)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Не удалось создать папку:\n{exc}")
            return

        self._set_busy(True)
        self.progress.set(0)
        self._set_status("Начинаю скачивание...")
        threading.Thread(
            target=self._download_worker,
            args=(url, folder, self.format_var.get()),
            daemon=True,
        ).start()

    def _download_worker(self, url: str, folder: Path, fmt: str):
        try:
            options = self._build_ydl_options(folder, fmt)
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
            self.after(0, lambda: self._download_done(folder))
        except Exception as exc:
            self.after(0, lambda: self._download_failed(str(exc)))

    def _build_ydl_options(self, folder: Path, fmt: str) -> dict:
        options = {
            "outtmpl": str(folder / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "ffmpeg_location": ffmpeg_path(),
            "progress_hooks": [self._progress_hook],
            "retries": 5,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 4,
            "noprogress": True,
        }

        if fmt == "mp3":
            options.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": self._selected_audio_quality(),
                        }
                    ],
                }
            )
            return options

        height = self._selected_height()
        height_filter = f"[height<={height}]" if height else ""
        options["format"] = (
            f"bestvideo{height_filter}[ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo{height_filter}+bestaudio/"
            f"best{height_filter}[ext=mp4]/"
            f"best{height_filter}"
        )
        options["merge_output_format"] = "mp4"
        return options

    def _progress_hook(self, data: dict):
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = (downloaded / total) if total else 0
            speed = format_size(data.get("speed"))
            eta = data.get("eta")
            parts = ["Скачивание"]
            if total:
                parts.append(f"{format_size(downloaded)} / {format_size(total)}")
            if speed:
                parts.append(f"{speed}/s")
            if eta is not None:
                parts.append(f"осталось {format_duration(eta)}")
            text = " · ".join(parts)
            self.after(0, lambda p=min(percent, 0.99), t=text: self._update_progress(p, t))
        elif status == "finished":
            self.after(0, lambda: self._update_progress(0.95, "Обработка файла..."))

    def _update_progress(self, value: float, text: str):
        self.progress.set(value)
        self._set_status(text)

    def _download_done(self, folder: Path):
        self.progress.set(1)
        self._set_status(f"Готово. Файл сохранён в: {folder}")
        self._set_busy(False)
        if messagebox.askyesno(APP_TITLE, f"Скачивание завершено.\nОткрыть папку?\n\n{folder}"):
            os.startfile(folder)

    def _download_failed(self, error: str):
        self.progress.set(0)
        self._set_status("Скачивание не удалось.")
        self._set_busy(False)
        messagebox.showerror(APP_TITLE, f"Ошибка скачивания:\n{error}")

    def _on_close(self):
        if self.is_busy and not messagebox.askyesno(
            APP_TITLE, "Идёт скачивание. Точно закрыть программу?"
        ):
            return
        self.destroy()


def main():
    app = YouTubeDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
