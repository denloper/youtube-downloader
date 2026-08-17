import io
import os
import re
import sys
import threading
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import imageio_ffmpeg
import yt_dlp
from PIL import Image, ImageDraw

APP_TITLE = "YouTube Downloader"
WINDOW_SIZE = "780x760"
YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+",
    re.IGNORECASE,
)
COMMON_HEIGHTS = (2160, 1440, 1080, 720, 480, 360, 240)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG = "#0a0c11"
CARD = "#12151d"
CARD_HL = "#171b24"
INSET = "#1b202b"
BORDER = "#242b39"
BORDER_SOFT = "#1d2431"
ACCENT = "#ff3b30"
ACCENT_HOVER = "#e12b22"
ACCENT_SOFT = "#2a1518"
GHOST = "#222836"
GHOST_HOVER = "#2b3242"
TEXT = "#f5f7fb"
TEXT_SUB = "#9aa4b2"
TEXT_MUT = "#5f6875"

_SS = 4  # supersampling factor for crisp icons


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


# ---------------------------------------------------------------------------
# Icon factory — all icons are drawn with PIL primitives so they render
# crisply on any platform without depending on emoji/icon fonts.
# ---------------------------------------------------------------------------
def _canvas(size: int):
    img = Image.new("RGBA", (size * _SS, size * _SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), size * _SS


def _finish(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def _rline(draw: ImageDraw.ImageDraw, p1, p2, width, color):
    draw.line([p1, p2], fill=color, width=width)
    r = width / 2
    for x, y in (p1, p2):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def icon_logo(size: int = 46, radius: int = 13, color: str = ACCENT) -> Image.Image:
    img, d, S = _canvas(size)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=radius * _SS, fill=color)
    w, h = S * 0.28, S * 0.32
    cx, cy = S * 0.545, S * 0.5
    d.polygon(
        [(cx - w / 2, cy - h / 2), (cx - w / 2, cy + h / 2), (cx + w / 2, cy)],
        fill="#ffffff",
    )
    return _finish(img, size)


def icon_download(size: int = 18, color: str = "#ffffff") -> Image.Image:
    img, d, S = _canvas(size)
    lw = max(2, int(S * 0.085))
    cx = S * 0.5
    _rline(d, (cx, S * 0.16), (cx, S * 0.6), lw, color)
    _rline(d, (S * 0.30, S * 0.44), (cx, S * 0.63), lw, color)
    _rline(d, (S * 0.70, S * 0.44), (cx, S * 0.63), lw, color)
    _rline(d, (S * 0.22, S * 0.82), (S * 0.78, S * 0.82), lw, color)
    return _finish(img, size)


def icon_search(size: int = 18, color: str = ACCENT) -> Image.Image:
    img, d, S = _canvas(size)
    lw = max(2, int(S * 0.085))
    box = [S * 0.18, S * 0.18, S * 0.64, S * 0.64]
    d.ellipse(box, outline=color, width=lw)
    _rline(d, (S * 0.60, S * 0.60), (S * 0.84, S * 0.84), lw, color)
    return _finish(img, size)


def icon_paste(size: int = 16, color: str = TEXT_SUB) -> Image.Image:
    img, d, S = _canvas(size)
    lw = max(2, int(S * 0.08))
    d.rounded_rectangle(
        [S * 0.24, S * 0.18, S * 0.78, S * 0.86], radius=S * 0.1, outline=color, width=lw
    )
    d.rounded_rectangle(
        [S * 0.38, S * 0.10, S * 0.64, S * 0.26], radius=S * 0.05, fill=color
    )
    return _finish(img, size)


def icon_folder(size: int = 16, color: str = TEXT_SUB) -> Image.Image:
    img, d, S = _canvas(size)
    lw = max(2, int(S * 0.08))
    d.line([(S * 0.16, S * 0.30), (S * 0.44, S * 0.30)], fill=color, width=lw)
    d.line([(S * 0.44, S * 0.30), (S * 0.52, S * 0.40)], fill=color, width=lw)
    d.rounded_rectangle(
        [S * 0.16, S * 0.34, S * 0.84, S * 0.78], radius=S * 0.08, outline=color, width=lw
    )
    return _finish(img, size)


def icon_photo(size: int = 44, color: str = "#3a4152") -> Image.Image:
    img, d, S = _canvas(size)
    lw = max(2, int(S * 0.05))
    d.rounded_rectangle(
        [S * 0.12, S * 0.18, S * 0.88, S * 0.82], radius=S * 0.1, outline=color, width=lw
    )
    d.ellipse([S * 0.24, S * 0.30, S * 0.40, S * 0.46], fill=color)
    d.polygon(
        [
            (S * 0.20, S * 0.74),
            (S * 0.44, S * 0.50),
            (S * 0.60, S * 0.66),
            (S * 0.72, S * 0.54),
            (S * 0.86, S * 0.74),
        ],
        fill=color,
    )
    return _finish(img, size)


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255
    )
    img.putalpha(mask)
    return img


def _fit_cover(img: Image.Image, target) -> Image.Image:
    tw, th = target
    w, h = img.size
    scale = max(tw / w, th / h)
    img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    left = (img.size[0] - tw) // 2
    top = (img.size[1] - th) // 2
    return img.crop((left, top, left + tw, top + th))


THUMB_SIZE = (248, 140)


class YouTubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(720, 640)
        self.configure(fg_color=BG)

        self.video_info = None
        self.available_heights = []
        self.is_busy = False
        self.download_dir = default_download_dir()
        self._thumb_token = 0
        self._thumb_image = None

        self._build_icons()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ icons
    def _img(self, pil: Image.Image, size) -> ctk.CTkImage:
        if isinstance(size, int):
            size = (size, size)
        return ctk.CTkImage(light_image=pil, dark_image=pil, size=size)

    def _build_icons(self):
        self.ic_logo = self._img(icon_logo(46), 46)
        self.ic_download = self._img(icon_download(18), 18)
        self.ic_search = self._img(icon_search(18), 18)
        self.ic_paste = self._img(icon_paste(16), 16)
        self.ic_folder = self._img(icon_folder(16), 16)
        self.ic_photo = self._img(icon_photo(46), 46)

    # --------------------------------------------------------------------- ui
    def _build_ui(self):
        container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color="#242b39",
            scrollbar_button_hover_color="#313a4d",
        )
        container.pack(fill="both", expand=True, padx=26, pady=(22, 20))

        self._build_header(container)
        self._build_url_card(container)
        self._build_preview_card(container)
        self._build_options_card(container)
        self._build_progress_card(container)

        self.download_button = ctk.CTkButton(
            container,
            text="Скачать",
            image=self.ic_download,
            compound="left",
            height=52,
            corner_radius=13,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self.start_download,
        )
        self.download_button.pack(fill="x", pady=(4, 8))

    def _build_header(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))

        logo = ctk.CTkLabel(header, text="", image=self.ic_logo)
        logo.pack(side="left", padx=(0, 14))

        text_col = ctk.CTkFrame(header, fg_color="transparent")
        text_col.pack(side="left", anchor="center", fill="y")
        ctk.CTkLabel(
            text_col,
            text="YouTube Downloader",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_col,
            text="Скачивайте видео и аудио с YouTube в пару кликов",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SUB,
        ).pack(anchor="w", pady=(3, 0))

    def _build_url_card(self, parent):
        card = self._card(parent)
        self._card_title(card, "Ссылка на видео")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", pady=(12, 12))

        self.url_entry = ctk.CTkEntry(
            row,
            height=46,
            corner_radius=11,
            placeholder_text="https://www.youtube.com/watch?v=...",
            font=ctk.CTkFont(size=13),
            fg_color=INSET,
            border_color=BORDER,
            border_width=1,
        )
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.url_entry.bind("<Return>", lambda _e: self.fetch_info())

        ctk.CTkButton(
            row,
            text="Вставить",
            image=self.ic_paste,
            compound="left",
            width=118,
            height=46,
            corner_radius=11,
            fg_color=GHOST,
            hover_color=GHOST_HOVER,
            text_color=TEXT,
            font=ctk.CTkFont(size=13),
            command=self.paste_url,
        ).pack(side="left", padx=(10, 0))

        self.fetch_button = ctk.CTkButton(
            card,
            text="Получить информацию",
            image=self.ic_search,
            compound="left",
            height=44,
            corner_radius=11,
            fg_color="transparent",
            hover_color=ACCENT_SOFT,
            border_color=ACCENT,
            border_width=2,
            text_color=ACCENT,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.fetch_info,
        )
        self.fetch_button.pack(fill="x")

    def _build_preview_card(self, parent):
        card = self._card(parent)
        self._card_title(card, "Информация о видео")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", pady=(14, 2))

        self.thumb_frame = ctk.CTkFrame(
            body,
            width=THUMB_SIZE[0],
            height=THUMB_SIZE[1],
            corner_radius=12,
            fg_color=INSET,
            border_color=BORDER,
            border_width=1,
        )
        self.thumb_frame.pack(side="left")
        self.thumb_frame.pack_propagate(False)

        self.thumb_label = ctk.CTkLabel(
            self.thumb_frame, text="", image=self.ic_photo
        )
        self.thumb_label.pack(expand=True)
        self.thumb_hint = ctk.CTkLabel(
            self.thumb_frame,
            text="Превью появится\nпосле загрузки",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUT,
        )
        self.thumb_hint.pack(pady=(0, 14))

        details = ctk.CTkFrame(body, fg_color="transparent")
        details.pack(side="left", fill="both", expand=True, padx=(16, 0))

        self.title_label = ctk.CTkLabel(
            details,
            text="Видео ещё не выбрано",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT,
            wraplength=380,
            justify="left",
            anchor="w",
        )
        self.title_label.pack(anchor="w", fill="x")

        self.channel_label = self._meta_row(details, "Канал", "—")
        self.duration_label = self._meta_row(details, "Длительность", "—")

    def _build_options_card(self, parent):
        card = self._card(parent)
        self._card_title(card, "Параметры скачивания")

        self._field_label(card, "Формат", (14, 6))
        self.format_var = ctk.StringVar(value="mp4")
        self.mp4_button = ctk.CTkSegmentedButton(
            card,
            values=["MP4", "MP3"],
            command=self._on_format_change,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=INSET,
            unselected_hover_color=GHOST,
            text_color=TEXT,
            corner_radius=10,
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.mp4_button.set("MP4")
        self.mp4_button.pack(fill="x")

        self._field_label(card, "Разрешение / качество", (16, 6))
        self.quality_menu = ctk.CTkOptionMenu(
            card,
            values=["Сначала получите информацию о видео"],
            height=42,
            corner_radius=10,
            fg_color=INSET,
            button_color=GHOST,
            button_hover_color=GHOST_HOVER,
            dropdown_fg_color=CARD_HL,
            dropdown_hover_color=GHOST,
            text_color=TEXT,
            font=ctk.CTkFont(size=13),
        )
        self.quality_menu.set("Сначала получите информацию о видео")
        self.quality_menu.pack(fill="x")

        self._field_label(card, "Папка сохранения", (16, 6))
        folder_row = ctk.CTkFrame(card, fg_color="transparent")
        folder_row.pack(fill="x")

        self.folder_entry = ctk.CTkEntry(
            folder_row,
            height=42,
            corner_radius=10,
            fg_color=INSET,
            border_color=BORDER,
            border_width=1,
            font=ctk.CTkFont(size=13),
        )
        self.folder_entry.insert(0, str(self.download_dir))
        self.folder_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            folder_row,
            text="Обзор",
            image=self.ic_folder,
            compound="left",
            width=108,
            height=42,
            corner_radius=10,
            fg_color=GHOST,
            hover_color=GHOST_HOVER,
            text_color=TEXT,
            font=ctk.CTkFont(size=13),
            command=self.choose_folder,
        ).pack(side="left", padx=(10, 0))

    def _build_progress_card(self, parent):
        card = self._card(parent)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x")
        self.status_label = ctk.CTkLabel(
            top,
            text="Вставьте ссылку и нажмите «Получить информацию»",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SUB,
            wraplength=560,
            justify="left",
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.percent_label = ctk.CTkLabel(
            top,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ACCENT,
        )
        self.percent_label.pack(side="right")

        self.progress = ctk.CTkProgressBar(
            card,
            height=10,
            corner_radius=6,
            progress_color=ACCENT,
            fg_color=INSET,
        )
        self.progress.pack(fill="x", pady=(14, 2))
        self.progress.set(0)

    # ---------------------------------------------------------------- helpers
    def _card(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color=CARD,
            border_color=BORDER_SOFT,
            border_width=1,
            corner_radius=16,
        )
        card.pack(fill="x", pady=(0, 16))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=18)
        return inner

    def _card_title(self, parent, text):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        bar = ctk.CTkFrame(row, width=4, height=18, corner_radius=2, fg_color=ACCENT)
        bar.pack(side="left", padx=(0, 10))
        bar.pack_propagate(False)
        ctk.CTkLabel(
            row,
            text=text,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        ).pack(side="left")

    def _field_label(self, parent, text, pady):
        ctk.CTkLabel(
            parent,
            text=text.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUT,
        ).pack(anchor="w", pady=pady)

    def _meta_row(self, parent, title, value):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(anchor="w", fill="x", pady=(12, 0))
        ctk.CTkLabel(
            wrap,
            text=title.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUT,
        ).pack(anchor="w")
        value_label = ctk.CTkLabel(
            wrap,
            text=value,
            font=ctk.CTkFont(size=14),
            text_color=TEXT,
            wraplength=380,
            justify="left",
            anchor="w",
        )
        value_label.pack(anchor="w")
        return value_label

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

    # -------------------------------------------------------------- fetch info
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
        self.percent_label.configure(text="")
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
        self.channel_label.configure(
            text=info.get("uploader") or info.get("channel") or "—"
        )
        self.duration_label.configure(text=format_duration(info.get("duration")))
        self._refresh_quality_options()
        self._set_status("Информация получена. Выберите формат и нажмите «Скачать».")
        self._set_busy(False)
        self._start_thumbnail(info)

    def _fetch_failed(self, error: str):
        self.video_info = None
        self._set_status("Не удалось получить информацию о видео.")
        self._set_busy(False)
        messagebox.showerror(APP_TITLE, f"Ошибка при получении информации:\n{error}")

    # -------------------------------------------------------------- thumbnail
    def _start_thumbnail(self, info: dict):
        url = self._best_thumbnail(info)
        self._thumb_token += 1
        token = self._thumb_token
        if not url:
            self._reset_thumbnail()
            return
        threading.Thread(
            target=self._thumbnail_worker, args=(url, token), daemon=True
        ).start()

    def _best_thumbnail(self, info: dict):
        thumbs = info.get("thumbnails") or []
        best, best_area = None, -1
        for t in thumbs:
            u = t.get("url")
            if not u:
                continue
            area = (t.get("width") or 0) * (t.get("height") or 0)
            if area >= best_area:
                best, best_area = u, area
        return best or info.get("thumbnail")

    def _thumbnail_worker(self, url: str, token: int):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img = _rounded(_fit_cover(img, THUMB_SIZE), 12)
            self.after(0, lambda: self._set_thumbnail(img, token))
        except Exception:
            self.after(0, self._reset_thumbnail)

    def _set_thumbnail(self, img: Image.Image, token: int):
        if token != self._thumb_token:
            return
        self.thumb_hint.pack_forget()
        self._thumb_image = ctk.CTkImage(
            light_image=img, dark_image=img, size=THUMB_SIZE
        )
        self.thumb_label.configure(image=self._thumb_image)
        self.thumb_label.pack(expand=True, fill="both")

    def _reset_thumbnail(self):
        self._thumb_image = None
        self.thumb_label.configure(image=self.ic_photo)
        self.thumb_label.pack(expand=True)
        self.thumb_hint.pack(pady=(0, 14))

    # ------------------------------------------------------------------ format
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

    # ------------------------------------------------------------------ download
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
        self.percent_label.configure(text="0%")
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
            self.after(
                0, lambda p=min(percent, 0.99), t=text: self._update_progress(p, t)
            )
        elif status == "finished":
            self.after(0, lambda: self._update_progress(0.97, "Обработка файла..."))

    def _update_progress(self, value: float, text: str):
        self.progress.set(value)
        self.percent_label.configure(text=f"{int(value * 100)}%")
        self._set_status(text)

    def _download_done(self, folder: Path):
        self.progress.set(1)
        self.percent_label.configure(text="100%")
        self._set_status(f"Готово. Файл сохранён в: {folder}")
        self._set_busy(False)
        if messagebox.askyesno(
            APP_TITLE, f"Скачивание завершено.\nОткрыть папку?\n\n{folder}"
        ):
            self._open_folder(folder)

    def _open_folder(self, folder: Path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception:
            pass

    def _download_failed(self, error: str):
        self.progress.set(0)
        self.percent_label.configure(text="")
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
