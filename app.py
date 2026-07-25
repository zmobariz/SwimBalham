"""
Swim Balham — Sessions & Availability Viewer (v4 — Modern UI).

A polished desktop app showing live session and facility availability
for Balham Leisure Centre and Tooting Bec Lido. Loads instantly from a
local cache, then refreshes from the OpenActive RPDE API.
"""

import customtkinter as ctk
import threading
import sys
import os
import json
import webbrowser
import winsound
import ctypes
import tkinter.font as tkfont
from tkinter import TclError
from datetime import timedelta

APP_VERSION = "1.0.2"
SUPPORT_URL = "https://ko-fi.com/syrexeno"
SUPPORT_MESSAGE = (
    "Swim Balham helps you find an available swimming slot and alerts you when a "
    "space opens, so you can spend less time checking timetables and more time "
    "getting in the pool.\n\n"
    "If the app has helped you secure a session, stay organised, or avoid missing "
    "a swim, you can support its continued development by buying me a coffee.\n\n"
    "Your support helps cover the cost of keeping the app running, improving "
    "reminders, and making it even easier to find your next swim.\n\n"
    "Enjoy your session — and thank you for supporting Swim Balham."
)

# Set Windows AppUserModelID so the taskbar shows our icon, not Python's.
# This MUST be called before any Tkinter window is created.
if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SwimBalham.App.v1")
    except Exception:
        pass

# PIL imports — try the right Python's site-packages first
try:
    from PIL import Image, ImageTk
except ImportError:
    try:
        if sys.prefix:
            import importlib
            pil_path = os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages")
            if pil_path not in sys.path:
                sys.path.insert(0, pil_path)
        from PIL import Image, ImageTk
    except ImportError:
        Image = None
        ImageTk = None

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SETTINGS = {
    "refresh_interval_minutes": 5,
    "lookahead_days": 1,
}

sys.path.insert(0, APP_DIR)
from api_client import PlacesLeisureClient, DataCache, to_uk_local, uk_now, CENTRES, DATA_DIR

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LEGACY_SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")

# ─── Modern Theme — Aquatic Blue Palette ──────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Brand colours inspired by the Swim Balham logo
C = {
    # Backgrounds
    "bg": "#0A1628",             # Deep navy
    "bg_surface": "#0F1F38",     # Card surface
    "bg_surface2": "#142B4D",    # Elevated surface
    "bg_hover": "#1A3556",       # Hover state
    "sidebar": "#0D1A30",        # Sidebar background

    # Accents
    "primary": "#1A8FE3",        # Bright ocean blue
    "primary_hover": "#1579C4",  # Darker blue on hover
    "primary_dim": "#0E5A8A",    # Muted blue
    "cyan": "#22D3EE",           # Cyan accent (bubbles)

    # Text
    "text": "#F0F6FF",           # Near-white with blue tint
    "text_secondary": "#7B9CC4", # Muted blue-grey
    "text_dim": "#4A6B8A",       # Dim text

    # Status colours
    "success": "#10B981",        # Green
    "success_bg": "#062018",
    "warning": "#F59E0B",        # Amber
    "warning_bg": "#221A06",
    "danger": "#EF4444",         # Red
    "danger_bg": "#220808",

    # Lines & borders
    "border": "#1C3358",         # Subtle border
    "border_light": "#244B7A",   # Lighter border
}

ROW_HEIGHT = 82
FONT_TEXT = "Segoe UI"
FONT_DISPLAY = "Segoe UI"


def _init_fonts():
    """Detect the best available font family."""
    global FONT_TEXT, FONT_DISPLAY
    families = set(tkfont.families())
    if "Segoe UI Variable Text" in families and "Segoe UI Variable Display" in families:
        FONT_TEXT = "Segoe UI Variable Text"
        FONT_DISPLAY = "Segoe UI Variable Display"


def fmt_time(dt):
    if not dt:
        return "--:--"
    return to_uk_local(dt).strftime("%H:%M")

def fmt_date(dt):
    if not dt:
        return "—"
    local = to_uk_local(dt)
    today = uk_now().date()
    if local.date() == today:
        return "Today"
    if local.date() == today + timedelta(days=1):
        return "Tomorrow"
    return local.strftime("%a %d %b")

def fmt_date_long(dt):
    if not dt:
        return "—"
    return to_uk_local(dt).strftime("%A %d %B %Y")

def avail_info(item):
    remaining = item.get("remaining")
    max_cap = item.get("max_capacity")
    if remaining is None:
        return {"colour": C["text_secondary"], "bg": C["bg_surface2"], "label": "N/A", "pct": 0}
    pct = (remaining / max_cap * 100) if max_cap and max_cap > 0 else (100 if remaining > 0 else 0)
    if remaining == 0:
        return {"colour": C["danger"], "bg": C["danger_bg"], "label": "FULL", "pct": 0}
    if pct <= 25:
        return {"colour": C["warning"], "bg": C["warning_bg"], "label": f"{remaining} left", "pct": pct}
    return {"colour": C["success"], "bg": C["success_bg"], "label": f"{remaining} avail", "pct": pct}


# ─── Settings persistence ─────────────────────────────────────────────────
def load_settings():
    for path in (SETTINGS_FILE, LEGACY_SETTINGS_FILE):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings = {**DEFAULT_SETTINGS, **saved}
            if path != SETTINGS_FILE:
                save_settings(settings)
            return settings
        except (OSError, ValueError):
            continue
    return dict(DEFAULT_SETTINGS)

def save_settings(settings):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        print(f"[Settings] Save error: {e}")


# ─── Settings Dialog ──────────────────────────────────────────────────────
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, current_settings, on_save=None):
        super().__init__(master)
        self.on_save = on_save
        self.result = dict(current_settings)

        self.title("Settings")
        self.geometry("440x380")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.attributes("-topmost", True)
        self.transient(master)
        self.grab_set()

        # Header
        ctk.CTkLabel(self, text="⚙  Settings",
                     font=ctk.CTkFont(family=FONT_DISPLAY, size=15, weight="bold"),
                     text_color=C["text"]).pack(fill="x", padx=28, pady=(24, 20))

        # Refresh interval
        ri_frame = ctk.CTkFrame(self, fg_color="transparent")
        ri_frame.pack(fill="x", padx=28, pady=(0, 4))
        ctk.CTkLabel(ri_frame, text="Auto-refresh interval",
                     font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                     text_color=C["text"], anchor="w").pack(fill="x")
        ctk.CTkLabel(ri_frame, text="How often to check for new availability",
                     font=ctk.CTkFont(family=FONT_TEXT, size=11),
                     text_color=C["text_secondary"], anchor="w").pack(fill="x", pady=(0, 8))
        ri_row = ctk.CTkFrame(ri_frame, fg_color="transparent")
        ri_row.pack(fill="x")
        self.ri_slider = ctk.CTkSlider(ri_row, from_=1, to=60, number_of_steps=59,
                                       width=240, height=20,
                                       fg_color=C["bg_surface2"],
                                       progress_color=C["primary"],
                                       button_color=C["cyan"], button_hover_color=C["primary"])
        self.ri_slider.set(current_settings.get("refresh_interval_minutes", 5))
        self.ri_slider.pack(side="left")
        self.ri_label = ctk.CTkLabel(ri_row, text=self._fmt_minutes(int(self.ri_slider.get())),
                                     font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                                     text_color=C["cyan"], width=80, anchor="e")
        self.ri_label.pack(side="left", padx=(8, 0))
        self.ri_slider.configure(command=lambda v: self.ri_label.configure(text=self._fmt_minutes(int(v))))

        # Lookahead days
        la_frame = ctk.CTkFrame(self, fg_color="transparent")
        la_frame.pack(fill="x", padx=28, pady=(16, 4))
        ctk.CTkLabel(la_frame, text="Days to look ahead",
                     font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                     text_color=C["text"], anchor="w").pack(fill="x")
        ctk.CTkLabel(la_frame, text="How many days of future sessions to show",
                     font=ctk.CTkFont(family=FONT_TEXT, size=11),
                     text_color=C["text_secondary"], anchor="w").pack(fill="x", pady=(0, 8))
        la_row = ctk.CTkFrame(la_frame, fg_color="transparent")
        la_row.pack(fill="x")
        self.la_slider = ctk.CTkSlider(la_row, from_=1, to=14, number_of_steps=13,
                                       width=240, height=20,
                                       fg_color=C["bg_surface2"],
                                       progress_color=C["primary"],
                                       button_color=C["cyan"], button_hover_color=C["primary"])
        self.la_slider.set(current_settings.get("lookahead_days", 14))
        self.la_slider.pack(side="left")
        self.la_label = ctk.CTkLabel(la_row, text=self._fmt_days(int(self.la_slider.get())),
                                     font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                                     text_color=C["cyan"], width=80, anchor="e")
        self.la_label.pack(side="left", padx=(8, 0))
        self.la_slider.configure(command=lambda v: self.la_label.configure(text=self._fmt_days(int(v))))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=28, pady=(28, 28), side="bottom")
        ctk.CTkButton(btn_row, text="Cancel", font=ctk.CTkFont(family=FONT_TEXT, size=13, weight="bold"),
                      fg_color=C["bg_surface2"], hover_color=C["border"], text_color=C["text_secondary"],
                      height=42, corner_radius=10,
                      command=self.destroy).pack(side="left", expand=True, fill="x", padx=(0, 10))
        ctk.CTkButton(btn_row, text="Save", font=ctk.CTkFont(family=FONT_TEXT, size=13, weight="bold"),
                      fg_color=C["primary"], hover_color=C["primary_hover"],
                      height=42, corner_radius=10,
                      command=self._on_save).pack(side="left", expand=True, fill="x", padx=(10, 0))

    @staticmethod
    def _fmt_minutes(m):
        if m == 1: return "1 min"
        if m < 60: return f"{m} mins"
        return "1 hour"

    @staticmethod
    def _fmt_days(d):
        return f"{d} {'day' if d == 1 else 'days'}"

    def _on_save(self):
        self.result["refresh_interval_minutes"] = int(self.ri_slider.get())
        self.result["lookahead_days"] = int(self.la_slider.get())
        save_settings(self.result)
        if self.on_save:
            self.on_save(self.result)
        self.destroy()


class SupportDialog(ctk.CTkToplevel):
    """Keep the project support message available from the main app."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Support Swim Balham")
        self.geometry("520x470")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.attributes("-topmost", True)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="Found your swim? Brilliant.",
            font=ctk.CTkFont(family=FONT_DISPLAY, size=20, weight="bold"),
            text_color=C["text"],
            anchor="w",
        ).pack(fill="x", padx=28, pady=(28, 10))

        ctk.CTkLabel(
            self,
            text=SUPPORT_MESSAGE,
            font=ctk.CTkFont(family=FONT_TEXT, size=13),
            text_color=C["text_secondary"],
            anchor="nw",
            justify="left",
            wraplength=464,
        ).pack(fill="both", expand=True, padx=28)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=28, pady=28, side="bottom")
        ctk.CTkButton(
            buttons,
            text="☕ Buy me a coffee ↗",
            font=ctk.CTkFont(family=FONT_TEXT, size=12, weight="bold"),
            fg_color=C["warning"],
            hover_color="#D97706",
            text_color=C["bg"],
            height=36,
            corner_radius=10,
            command=lambda: webbrowser.open(SUPPORT_URL),
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            buttons,
            text="Close",
            font=ctk.CTkFont(family=FONT_TEXT, size=12, weight="bold"),
            fg_color=C["bg_surface2"],
            hover_color=C["border"],
            width=90,
            height=36,
            corner_radius=10,
            command=self.destroy,
        ).pack(side="left", padx=(6, 0))


# ─── Virtualised List (Canvas-based) ──────────────────────────────────────
class VirtualList(ctk.CTkFrame):
    """High-performance virtualised list — draws only visible rows on a Canvas."""

    def __init__(self, master, row_height=ROW_HEIGHT, on_select=None, **kw):
        super().__init__(master, **kw)
        self.row_height = row_height
        self.on_select = on_select
        self._items = []
        self._scroll_offset = 0
        self._hovered_row = -1
        self._selected_row = -1
        self._show_centre = False

        self.canvas = ctk.CTkCanvas(self, bg=C["bg"], highlightthickness=0, borderwidth=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.bind("<Configure>", lambda e: self._render())

    def set_items(self, items):
        self._items = items
        self._scroll_offset = 0
        self._render()

    def _on_wheel(self, event):
        delta = -int(event.delta / 120) * 48
        self._scroll(delta)

    def _scroll(self, delta):
        max_scroll = max(0, len(self._items) * self.row_height - self.canvas.winfo_height())
        new_offset = max(0, min(max_scroll, self._scroll_offset + delta))
        if new_offset != self._scroll_offset:
            self._scroll_offset = new_offset
            self._render()

    def _on_click(self, event):
        y = event.y + self._scroll_offset
        row = int(y // self.row_height)
        if 0 <= row < len(self._items):
            self._selected_row = row
            self._render()
            if self.on_select:
                self.on_select(self._items[row])

    def _on_motion(self, event):
        y = event.y + self._scroll_offset
        row = int(y // self.row_height)
        if row != self._hovered_row:
            self._hovered_row = row
            self._render()

    def _on_leave(self, event):
        self._hovered_row = -1
        self._render()

    def _render(self):
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        if not self._items:
            self.canvas.create_text(
                cw // 2, ch // 2,
                text="No results match your filters.",
                fill=C["text_secondary"], font=(FONT_TEXT, 11))
            return

        first = max(0, self._scroll_offset // self.row_height)
        last = min(len(self._items), (self._scroll_offset + ch) // self.row_height + 1)

        for i in range(first, last):
            item = self._items[i]
            y = i * self.row_height - self._scroll_offset
            is_selected = (i == self._selected_row)
            is_hover = (i == self._hovered_row)
            a = avail_info(item)
            is_fac = item.get("type") == "slot"
            rh = self.row_height

            # ── Card background with rounded corners ──
            x1, y1, x2, y2 = 4, y + 3, cw - 4, y + rh - 5
            if is_selected or is_hover:
                bg = C["bg_hover"]
            else:
                bg = C["bg_surface"]
            r = 8
            self.canvas.create_rectangle(x1 + r, y1, x2 - r, y1 + r, fill=bg, outline="")
            self.canvas.create_rectangle(x1 + r, y2 - r, x2 - r, y2, fill=bg, outline="")
            self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=bg, outline="")
            self.canvas.create_oval(x1, y1, x1 + 2*r, y1 + 2*r, fill=bg, outline="")
            self.canvas.create_oval(x2 - 2*r, y1, x2, y1 + 2*r, fill=bg, outline="")
            self.canvas.create_oval(x1, y2 - 2*r, x1 + 2*r, y2, fill=bg, outline="")
            self.canvas.create_oval(x2 - 2*r, y2 - 2*r, x2, y2, fill=bg, outline="")
            # Accent line on left when selected
            if is_selected:
                self.canvas.create_rectangle(x1 + 2, y1 + 6, x1 + 4, y2 - 6, fill=C["primary"], outline="")

            # ── LEFT COLUMN: Time + Duration ──
            time_y = y + 14
            self.canvas.create_text(18, time_y, text=fmt_time(item.get("start")),
                                    fill=C["cyan"], font=(FONT_TEXT, 13, "bold"), anchor="nw")
            dur = item.get("duration_minutes")
            if dur:
                self.canvas.create_text(18, time_y + 18, text=f"{dur}min",
                                        fill=C["text_dim"], font=(FONT_TEXT, 9), anchor="nw")

            # ── MAIN COLUMN: Name + details ──
            mx = 75
            self.canvas.create_text(mx, time_y, text=item.get("name", "Session"),
                                    fill=C["text"], font=(FONT_TEXT, 12, "bold"), anchor="nw")

            # Second line: date + centre
            my2 = time_y + 18
            parts = []
            d = fmt_date(item.get("start"))
            if d != "—":
                parts.append(d)
            if item.get("centre_name") and self._show_centre:
                parts.append(item["centre_name"])
            if item.get("activity"):
                parts.append(item["activity"])
            if parts:
                self.canvas.create_text(mx, my2, text="  •  ".join(parts),
                                        fill=C["text_secondary"], font=(FONT_TEXT, 9), anchor="nw")

            # ── RIGHT COLUMN: Availability pill + price ──
            rx = cw - 20  # right edge

            # Price (top-right)
            price = item.get("price")
            ptext = ""
            if price is not None:
                ptext = "FREE" if price == 0 else f"£{price:.2f}"
            if ptext:
                self.canvas.create_text(rx, time_y, text=ptext,
                                        fill=C["text"], font=(FONT_TEXT, 11, "bold"), anchor="ne")

            # Type badge (right, below price)
            badge_text = "FACILITY" if is_fac else "SESSION"
            self.canvas.create_text(rx, my2 + 1, text=badge_text,
                                    fill=C["text_dim"], font=(FONT_TEXT, 7, "bold"), anchor="ne")

            # Availability pill (bottom-right)
            pill_label = a["label"]
            pill_font = (FONT_TEXT, 8, "bold")
            # Measure approximate text width (rough: avg char width ~ 5.5px at 8pt bold)
            pill_text_w = len(f"●  {pill_label}") * 5.5
            pill_w = int(pill_text_w + 16)
            pill_h = 16
            pr = 8
            px2 = rx
            px1 = px2 - pill_w
            py1 = y + rh - 22
            py2 = py1 + pill_h
            self.canvas.create_rectangle(px1 + pr, py1, px2 - pr, py1 + pr, fill=a["bg"], outline="")
            self.canvas.create_rectangle(px1 + pr, py2 - pr, px2 - pr, py2, fill=a["bg"], outline="")
            self.canvas.create_rectangle(px1, py1 + pr, px2, py2 - pr, fill=a["bg"], outline="")
            self.canvas.create_oval(px1, py1, px1 + 2*pr, py1 + 2*pr, fill=a["bg"], outline="")
            self.canvas.create_oval(px2 - 2*pr, py1, px2, py1 + 2*pr, fill=a["bg"], outline="")
            self.canvas.create_oval(px1, py2 - 2*pr, px1 + 2*pr, py2, fill=a["bg"], outline="")
            self.canvas.create_oval(px2 - 2*pr, py2 - 2*pr, px2, py2, fill=a["bg"], outline="")
            self.canvas.create_text((px1 + px2) // 2, (py1 + py2) // 2, text=f"●  {pill_label}",
                                    fill=a["colour"], font=pill_font, anchor="center")

            # Capacity bar (left of pill)
            if a["pct"] > 0:
                bar_w = 60
                bar_x = px1 - bar_w - 8
                bar_y = py1 + 4
                bar_h = 8
                br = 4
                # Track
                self.canvas.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h, fill=C["bg_surface2"], outline="")
                # Fill
                fill_w = max(br * 2, int(bar_w * a["pct"] / 100))
                self.canvas.create_rectangle(bar_x, bar_y, bar_x + fill_w, bar_y + bar_h, fill=a["colour"], outline="")


# ─── Detail Panel ─────────────────────────────────────────────────────────
class DetailPanel(ctk.CTkFrame):
    def __init__(self, master, app=None, **kw):
        super().__init__(master, **kw)
        self.app = app
        self.configure(fg_color=C["bg"], corner_radius=0)
        ctk.CTkLabel(self, text="Select a session to view details",
                     font=ctk.CTkFont(family=FONT_TEXT, size=13),
                     text_color=C["text_secondary"]).pack(pady=60)

    def show(self, item):
        for w in self.winfo_children():
            w.destroy()
        a = avail_info(item)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(scroll, text=item.get("name", "Session"),
                     font=ctk.CTkFont(family=FONT_DISPLAY, size=17, weight="bold"),
                     text_color=C["text"], anchor="w").pack(fill="x")

        start = item.get("start")
        end = item.get("end")
        if start:
            tr = f"{fmt_time(start)} – {fmt_time(end)}" if end else fmt_time(start)
            ctk.CTkLabel(scroll, text=f"📅  {fmt_date_long(start)}  •  {tr}",
                         font=ctk.CTkFont(family=FONT_TEXT, size=13),
                         text_color=C["text_secondary"], anchor="w").pack(fill="x", pady=(4, 0))

        loc = item.get("centre_name") or "Balham Leisure Centre"
        addr_parts = [loc]
        if item.get("address"):
            addr_parts.append(item["address"])
        ctk.CTkLabel(scroll, text=f"📍  {', '.join(addr_parts)}",
                     font=ctk.CTkFont(family=FONT_TEXT, size=13),
                     text_color=C["text_secondary"], anchor="w").pack(fill="x", pady=(4, 0))

        # Availability card
        af = ctk.CTkFrame(scroll, fg_color=a["bg"], corner_radius=14)
        af.pack(fill="x", pady=(20, 10))

        ctk.CTkLabel(af, text="  ●  AVAILABILITY",
                     font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                     text_color=a["colour"], anchor="w").pack(fill="x", padx=18, pady=(14, 0))

        remaining = item.get("remaining")
        max_cap = item.get("max_capacity")
        cap_text = f"{remaining} / {max_cap}" if remaining is not None and max_cap else a["label"]
        ctk.CTkLabel(af, text=cap_text,
                     font=ctk.CTkFont(family=FONT_DISPLAY, size=22, weight="bold"),
                     text_color=a["colour"], anchor="w").pack(fill="x", padx=18, pady=(0, 14))

        if a["pct"] > 0:
            bar = ctk.CTkProgressBar(af, height=8, corner_radius=4, fg_color=C["bg_surface2"],
                                     progress_color=a["colour"])
            bar.set(a["pct"] / 100)
            bar.pack(fill="x", padx=18, pady=(0, 14))

        # Book button
        book_url = item.get("url") or "https://www.placesleisure.org/centres/"
        ctk.CTkButton(
            scroll, text="Book this session ↗", font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
            fg_color=C["primary"], hover_color=C["primary_hover"], height=40, corner_radius=10,
            command=lambda u=book_url: webbrowser.open(u)).pack(fill="x", pady=(0, 10))

        # Reminder button
        if self.app is not None and item.get("remaining") == 0:
            watching = self.app.is_watching(item)
            ctk.CTkButton(
                scroll,
                text="🔕  Cancel reminder" if watching else "🔔  Remind me when available",
                font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                fg_color=C["bg_surface2"] if watching else C["warning"],
                hover_color=C["border"],
                text_color=C["text"] if watching else C["bg"],
                height=38, corner_radius=10,
                command=lambda it=item: self.app.toggle_watch(it)).pack(fill="x", pady=(0, 16))

        # Info grid
        info = []
        if item.get("activity"):
            info.append(("Activity", item["activity"]))
        if item.get("category"):
            info.append(("Category", item["category"]))
        if item.get("duration_minutes"):
            info.append(("Duration", f"{item['duration_minutes']} minutes"))
        if item.get("courts"):
            info.append(("Courts", ", ".join(item["courts"])))
        price = item.get("price")
        if price is not None:
            info.append(("Price", "FREE" if price == 0 else f"£{price:.2f}"))

        for label, value in info:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family=FONT_TEXT, size=12),
                         text_color=C["text_secondary"], width=100, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value, font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                         text_color=C["text"], anchor="w").pack(side="left", fill="x", expand=True)

        desc = item.get("description", "")
        if desc:
            ctk.CTkLabel(scroll, text="About", font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                         text_color=C["text"], anchor="w").pack(fill="x", pady=(20, 4))
            ctk.CTkLabel(scroll, text=desc.strip(),
                         font=ctk.CTkFont(family=FONT_TEXT, size=12),
                         text_color=C["text_secondary"], anchor="w",
                         wraplength=320, justify="left").pack(fill="x")


# ─── Main App ─────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        _init_fonts()
        self.title("Swim Balham")
        self.geometry("1240x800")
        self.minsize(900, 600)
        self.configure(fg_color=C["bg"])

        # Set window icon (taskbar + title bar)
        # Try .ico first (best quality on Windows), then fall back to PhotoImage
        try:
            if getattr(sys, 'frozen', False):
                icon_ico = os.path.join(sys._MEIPASS, "logo.ico")
                icon_png = os.path.join(sys._MEIPASS, "logo_header.png")
            else:
                icon_ico = os.path.join(APP_DIR, "logo.ico")
                icon_png = os.path.join(APP_DIR, "logo_header.png")

            if os.path.exists(icon_ico):
                self.iconbitmap(icon_ico)
            elif os.path.exists(icon_png) and ImageTk:
                # Fallback: set icon via PhotoImage (works for taskbar + alt-tab)
                self._icon_photo = ImageTk.PhotoImage(file=icon_png)
                self.iconphoto(True, self._icon_photo)
        except Exception as e:
            print(f"[Icon] Could not load: {e}")

        self.client = PlacesLeisureClient()
        self.cache = DataCache()
        self.loading = False
        self.auto_refresh = True
        self._auto_after_id = None
        self.watched = {}
        self.settings = load_settings()

        # Load header logo image
        self._logo_img = None
        self._sidebar_logo_img = None
        try:
            if getattr(sys, 'frozen', False):
                logo_path = os.path.join(sys._MEIPASS, "logo_header.png")
                sidebar_logo_path = os.path.join(sys._MEIPASS, "logo_sidebar.png")
            else:
                logo_path = os.path.join(APP_DIR, "logo_header.png")
                sidebar_logo_path = os.path.join(APP_DIR, "logo_sidebar.png")
            if os.path.exists(logo_path) and ImageTk:
                self._logo_img = ImageTk.PhotoImage(file=logo_path)
            if os.path.exists(sidebar_logo_path) and ImageTk:
                self._sidebar_logo_img = ImageTk.PhotoImage(file=sidebar_logo_path)
        except Exception:
            pass

        self._build_ui()

        if self.cache.load_from_disk():
            self._apply_filters()
            self.status_dot.configure(text_color=C["success"])
            self.status_label.configure(text="Cached — refreshing...")
        else:
            self._set_loading()

        self.after(200, self._start_fetch)

    def _build_ui(self):
        # ── Header bar ──
        header = ctk.CTkFrame(self, fg_color=C["sidebar"], height=48, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Logo + title
        header_left = ctk.CTkFrame(header, fg_color="transparent")
        header_left.pack(side="left", padx=20)

        if self._logo_img:
            ctk.CTkLabel(header_left, image=self._logo_img, text="").pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(header_left, text="🏊", font=ctk.CTkFont(size=16)).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(header_left, text="Swim Balham",
                     font=ctk.CTkFont(family=FONT_DISPLAY, size=14, weight="bold"),
                     text_color=C["text"]).pack(side="left")

        # Status (right side)
        self.status_dot = ctk.CTkLabel(header, text="●", font=ctk.CTkFont(size=12), text_color=C["text_secondary"])
        self.status_dot.pack(side="right", padx=(0, 6))
        self.status_label = ctk.CTkLabel(header, text="Connecting...",
                                         font=ctk.CTkFont(family=FONT_TEXT, size=12),
                                         text_color=C["text_secondary"])
        self.status_label.pack(side="right")

        # Settings button
        self.settings_btn = ctk.CTkButton(
            header, text="Settings", font=ctk.CTkFont(family=FONT_TEXT, size=11, weight="bold"),
            fg_color=C["bg_surface2"], hover_color=C["border"], text_color=C["text_secondary"],
            width=80, height=28, corner_radius=8,
            command=self._open_settings)
        self.settings_btn.pack(side="right", padx=(0, 8))

        self.support_btn = ctk.CTkButton(
            header, text="☕ Support", font=ctk.CTkFont(family=FONT_TEXT, size=11, weight="bold"),
            fg_color=C["warning"], hover_color="#D97706", text_color=C["bg"],
            width=88, height=28, corner_radius=8,
            command=self._open_support)
        self.support_btn.pack(side="right", padx=(0, 8))

        self.refresh_btn = ctk.CTkButton(
            header, text="↻ Refresh", font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
            fg_color=C["primary"], hover_color=C["primary_hover"], width=80, height=28, corner_radius=8,
            command=self._start_fetch)
        self.refresh_btn.pack(side="right", padx=(0, 8))

        ri = self.settings.get("refresh_interval_minutes", 5)
        self.auto_switch = ctk.CTkSwitch(header, text=f"Auto ({ri}m)",
                                         font=ctk.CTkFont(family=FONT_TEXT, size=11),
                                         text_color=C["text_secondary"],
                                         progress_color=C["primary"],
                                         fg_color=C["border"],
                                         button_color=C["cyan"],
                                         button_hover_color=C["primary"],
                                         command=self._toggle_auto)
        self.auto_switch.select()
        self.auto_switch.pack(side="right", padx=(0, 12))

        # ── Body ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self.detail = DetailPanel(body, app=self)
        self.detail.grid(row=0, column=2, sticky="nsew")
        body.grid_columnconfigure(2, minsize=360, weight=0)
        self._build_list(body)

    def _build_sidebar(self, parent):
        sb = ctk.CTkFrame(parent, fg_color=C["sidebar"], width=250, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.pack_propagate(False)

        # ── Logo at top of sidebar ──
        logo_frame = ctk.CTkFrame(sb, fg_color="transparent")
        logo_frame.pack(fill="x", padx=18, pady=(16, 4))
        logo_frame.pack_propagate(False)
        logo_frame.configure(height=64)

        if self._sidebar_logo_img:
            ctk.CTkLabel(logo_frame, image=self._sidebar_logo_img, text="").pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(logo_frame, text="🏊", font=ctk.CTkFont(size=24)).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(logo_frame, text="Swim Balham",
                     font=ctk.CTkFont(family=FONT_DISPLAY, size=14, weight="bold"),
                     text_color=C["text"]).pack(side="left")

        # Divider line
        ctk.CTkFrame(sb, fg_color=C["border"], height=1).pack(fill="x", padx=18, pady=(4, 12))

        # Centre selector
        self._label(sb, "CENTRE")
        centre_names = [CENTRES[k]["name"] for k in CENTRES]
        self.centre_var = ctk.StringVar(value="Balham Leisure Centre")
        self.centre_menu = ctk.CTkOptionMenu(
            sb, variable=self.centre_var, values=["All"] + centre_names,
            fg_color=C["bg_surface2"], button_color=C["bg_hover"],
            button_hover_color=C["border"], text_color=C["text"],
            dropdown_fg_color=C["bg_surface"], dropdown_hover_color=C["bg_hover"],
            dropdown_text_color=C["text"],
            height=30, corner_radius=8,
            command=lambda v: self._apply_filters())
        self.centre_menu.pack(fill="x", padx=18, pady=(0, 14))

        # View toggle
        self._label(sb, "VIEW")
        self.view_seg = ctk.CTkSegmentedButton(
            sb, values=["Sessions", "Facilities", "All"], command=lambda v: self._apply_filters(),
            fg_color=C["bg_surface2"], selected_color=C["primary"], selected_hover_color=C["primary_hover"],
            unselected_color=C["bg_hover"], unselected_hover_color=C["border"],
            text_color=C["text"], height=28, corner_radius=8)
        self.view_seg.set("Sessions")
        self.view_seg.pack(fill="x", padx=18, pady=(0, 14))

        # Search
        self.search = ctk.CTkEntry(sb, placeholder_text="Search sessions...",
                                   placeholder_text_color=C["text_dim"],
                                   font=ctk.CTkFont(family=FONT_TEXT, size=13), fg_color=C["bg_surface2"],
                                   border_color=C["border"], border_width=1,
                                   text_color=C["text"], height=28, corner_radius=8)
        self.search.pack(fill="x", padx=18, pady=(0, 14))
        self.search.bind("<KeyRelease>", lambda e: self._apply_filters())

        # Date filter
        self._label(sb, "DATE")
        self.date_var = ctk.StringVar(value="Any date")
        self.date_menu = ctk.CTkOptionMenu(
            sb, variable=self.date_var,
            values=["Any date", "Today", "Tomorrow", "Next 7 days", "Next 2 weeks",
                    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            fg_color=C["bg_surface2"], button_color=C["bg_hover"], button_hover_color=C["border"],
            text_color=C["text"],
            dropdown_fg_color=C["bg_surface"], dropdown_hover_color=C["bg_hover"],
            dropdown_text_color=C["text"],
            height=28, corner_radius=8, command=lambda v: self._apply_filters())
        self.date_menu.pack(fill="x", padx=18, pady=(0, 12))

        # Time-of-day
        self._label(sb, "TIME OF DAY")
        self.tod_seg = ctk.CTkSegmentedButton(
            sb, values=["All", "AM", "PM", "Eve"], command=lambda v: self._apply_filters(),
            fg_color=C["bg_surface2"], selected_color=C["primary"], selected_hover_color=C["primary_hover"],
            unselected_color=C["bg_hover"], unselected_hover_color=C["border"],
            text_color=C["text"], height=26, corner_radius=8)
        self.tod_seg.set("All")
        self.tod_seg.pack(fill="x", padx=18, pady=(0, 12))

        # Availability
        self._label(sb, "AVAILABILITY")
        self.avail_seg = ctk.CTkSegmentedButton(
            sb, values=["All", "Avail", "Full"], command=lambda v: self._apply_filters(),
            fg_color=C["bg_surface2"], selected_color=C["primary"], selected_hover_color=C["primary_hover"],
            unselected_color=C["bg_hover"], unselected_hover_color=C["border"],
            text_color=C["text"], height=26, corner_radius=8)
        self.avail_seg.set("All")
        self.avail_seg.pack(fill="x", padx=18, pady=(0, 12))

        # Category
        self._label(sb, "CATEGORY")
        self.f_category_var = ctk.StringVar(value="All")
        self.f_category = ctk.CTkOptionMenu(
            sb, variable=self.f_category_var, values=["All"],
            fg_color=C["bg_surface2"], button_color=C["bg_hover"], button_hover_color=C["border"],
            text_color=C["text"],
            dropdown_fg_color=C["bg_surface"], dropdown_hover_color=C["bg_hover"],
            dropdown_text_color=C["text"],
            height=28, corner_radius=8, command=lambda v: self._apply_filters())
        self.f_category.pack(fill="x", padx=18, pady=(0, 12))

        # Clear button
        ctk.CTkButton(sb, text="✕ Clear Filters", font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                      fg_color=C["bg_surface2"], hover_color=C["border"], text_color=C["text_secondary"],
                      height=26, corner_radius=8, command=self._clear_filters).pack(fill="x", padx=18, pady=(4, 12))

        self.stats = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(family=FONT_TEXT, size=10),
                                  text_color=C["text_secondary"], anchor="w", justify="left")
        self.stats.pack(side="bottom", fill="x", padx=18, pady=(18, 4))

        # Project note
        ctk.CTkLabel(sb, text=f"Independent community project  •  v{APP_VERSION}",
                     font=ctk.CTkFont(family=FONT_TEXT, size=9),
                     text_color=C["text_dim"], anchor="w").pack(side="bottom", fill="x", padx=18, pady=(0, 12))

    def _label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(family=FONT_TEXT, size=10, weight="bold"),
                     text_color=C["text_dim"], anchor="w").pack(fill="x", padx=18, pady=(0, 4))

    def _build_list(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=0, column=1, sticky="nsew", padx=14, pady=14)
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(container, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.title_lbl = ctk.CTkLabel(hdr, text="Sessions",
                                      font=ctk.CTkFont(family=FONT_DISPLAY, size=15, weight="bold"),
                                      text_color=C["text"], anchor="w")
        self.title_lbl.pack(side="left")
        self.count_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(family=FONT_TEXT, size=12),
                                      text_color=C["text_secondary"])
        self.count_lbl.pack(side="left", padx=(10, 0))

        self.vlist = VirtualList(container, on_select=self.detail.show)
        self.vlist._show_centre = True
        self.vlist.grid(row=1, column=0, sticky="nsew")

    def _set_loading(self):
        self.vlist.set_items([])

    # ── Fetch ──
    def _start_fetch(self):
        if self.loading:
            return
        self._cancel_auto_refresh()
        self.loading = True
        self.refresh_btn.configure(state="disabled", text="...")
        self.status_dot.configure(text_color=C["warning"])
        self.status_label.configure(text="Fetching...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            def progress(name, count):
                disp = {"session_series": "Templates", "scheduled_sessions": "Sessions",
                        "facility_uses": "Facilities", "slots": "Slots",
                        "booking_links": "Booking links"}.get(name, name)
                if count is None:
                    self.after(0, lambda d=disp: self.status_label.configure(text=f"Fetching {d}..."))
                else:
                    self.after(0, lambda d=disp, c=count: self.status_label.configure(text=f"{d}: {c}"))

            raw = self.client.fetch_all(progress_callback=progress,
                                        max_days=self.settings.get("lookahead_days", 1))
            self.cache.update(raw)
            self.cache.save_to_disk()
            self.after(0, self._on_done)
        except Exception as e:
            self.after(0, lambda: self._on_err(str(e)))

    def _on_done(self):
        self.loading = False
        self.refresh_btn.configure(state="normal", text="↻ Refresh")
        self.status_dot.configure(text_color=C["success"])
        last = self.cache.last_updated
        if last:
            self.status_label.configure(text=f"Updated {to_uk_local(last).strftime('%H:%M')}")
        self._refresh_dropdowns()
        self._apply_filters()
        self._check_watched()
        self._schedule_auto_refresh()

    def _on_err(self, err):
        self.loading = False
        self.refresh_btn.configure(state="normal", text="↻ Refresh")
        self.status_dot.configure(text_color=C["danger"])
        self.status_label.configure(text="Offline — showing cached")
        self._apply_filters()
        self._schedule_auto_refresh()
        print(f"[ERROR] {err}")

    def _auto_tick(self):
        self._auto_after_id = None
        if self.auto_refresh and not self.loading:
            self._start_fetch()

    def _cancel_auto_refresh(self):
        if self._auto_after_id is not None:
            try:
                self.after_cancel(self._auto_after_id)
            except (TclError, ValueError):
                pass
            self._auto_after_id = None

    def _schedule_auto_refresh(self):
        self._cancel_auto_refresh()
        if self.auto_refresh:
            interval_ms = self.settings.get("refresh_interval_minutes", 5) * 60_000
            self._auto_after_id = self.after(interval_ms, self._auto_tick)

    def _toggle_auto(self):
        self.auto_refresh = self.auto_switch.get() == 1
        if self.auto_refresh:
            self._schedule_auto_refresh()
        else:
            self._cancel_auto_refresh()

    def _open_settings(self):
        SettingsDialog(self, self.settings, on_save=self._on_settings_saved)

    def _open_support(self):
        SupportDialog(self)

    def _on_settings_saved(self, new_settings):
        self.settings = new_settings
        ri = new_settings.get("refresh_interval_minutes", 5)
        self.auto_switch.configure(text=f"Auto ({ri}m)")
        self._apply_filters()
        self._schedule_auto_refresh()

    # ── Reminders ──
    def _item_key(self, item):
        return f"{item.get('type')}:{item.get('id')}"

    def is_watching(self, item):
        return self._item_key(item) in self.watched

    def toggle_watch(self, item):
        key = self._item_key(item)
        if key in self.watched:
            del self.watched[key]
        else:
            self.watched[key] = dict(item)
        self.detail.show(item)

    def _check_watched(self):
        if not self.watched:
            return
        newly_available = []
        for key, watched_item in list(self.watched.items()):
            current = self.cache.find(watched_item.get("type"), watched_item.get("id"))
            if current and (current.get("remaining") or 0) > 0:
                newly_available.append(current)
                del self.watched[key]
        for item in newly_available:
            self._notify_available(item)

    def _notify_available(self, item):
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except OSError:
            pass
        self.deiconify()
        self.lift()
        self.focus_force()
        self._show_reminder_popup(item)

    def _show_reminder_popup(self, item):
        win = ctk.CTkToplevel(self)
        win.title("Found your swim? Brilliant.")
        win.geometry("520x520")
        win.resizable(False, False)
        win.configure(fg_color=C["bg"])
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="Found your swim? Brilliant.",
                     font=ctk.CTkFont(family=FONT_DISPLAY, size=20, weight="bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", padx=24, pady=(24, 8))

        when = f"{fmt_date(item.get('start'))}  •  {fmt_time(item.get('start'))}"
        event_card = ctk.CTkFrame(win, fg_color=C["success_bg"], corner_radius=12)
        event_card.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkLabel(event_card, text=f"A spot just opened up!\n{item.get('name', 'Session')}\n{when}",
                     font=ctk.CTkFont(family=FONT_TEXT, size=13),
                     text_color=C["success"], anchor="w", justify="left").pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(win, text=SUPPORT_MESSAGE,
                     font=ctk.CTkFont(family=FONT_TEXT, size=12),
                     text_color=C["text_secondary"], anchor="nw", justify="left",
                     wraplength=470).pack(fill="both", expand=True, padx=24)

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=24, side="bottom")
        url = item.get("url") or "https://www.placesleisure.org/centres/"
        ctk.CTkButton(btns, text="Book now ↗", fg_color=C["primary"], hover_color=C["primary_hover"],
                      corner_radius=10,
                      command=lambda: (webbrowser.open(url), win.destroy())).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(btns, text="☕ Buy me a coffee", fg_color=C["warning"], hover_color="#D97706",
                      text_color=C["bg"], corner_radius=10,
                      command=lambda: webbrowser.open(SUPPORT_URL)).pack(side="left", expand=True, fill="x", padx=6)
        ctk.CTkButton(btns, text="Dismiss", fg_color=C["bg_surface2"], hover_color=C["border"], width=76,
                      corner_radius=10,
                      command=win.destroy).pack(side="left", padx=(6, 0))

    def _clear_filters(self):
        self.search.delete(0, "end")
        self.f_category_var.set("All")
        self.date_var.set("Any date")
        self.tod_seg.set("All")
        self.avail_seg.set("All")
        self.view_seg.set("Sessions")
        self._apply_filters()

    def _refresh_dropdowns(self):
        cats = ["All"] + self.cache.categories
        self.f_category.configure(values=cats)
        if self.f_category_var.get() not in cats:
            self.f_category_var.set("All")

    def _build_filters(self):
        date_choice = self.date_var.get()
        today = uk_now().date()
        date_from = date_to = specific_date = None
        lookahead = self.settings.get("lookahead_days", 14)
        max_date = today + timedelta(days=lookahead)

        if date_choice == "Today":
            specific_date = today
        elif date_choice == "Tomorrow":
            specific_date = today + timedelta(days=1)
        elif date_choice == "Next 7 days":
            date_from = today
            date_to = min(today + timedelta(days=7), max_date)
        elif date_choice == "Next 2 weeks":
            date_from = today
            date_to = max_date
        elif date_choice in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
            target = day_map[date_choice]
            days_ahead = (target - today.weekday()) % 7
            specific_date = today + timedelta(days=days_ahead)

        tod_map = {"All": "all", "AM": "morning", "PM": "afternoon", "Eve": "evening"}

        if not specific_date and not date_to:
            date_to = max_date
        elif date_to and date_to > max_date:
            date_to = max_date

        return {
            "centre": self.centre_var.get(),
            "category": self.f_category_var.get(),
            "availability": self.avail_seg.get().lower(),
            "search": self.search.get(),
            "specific_date": specific_date,
            "date_from": date_from,
            "date_to": date_to,
            "time_of_day": tod_map.get(self.tod_seg.get(), "all"),
        }

    def _apply_filters(self):
        if self.cache.is_empty:
            return

        f = self._build_filters()
        view = self.view_seg.get().lower()
        items = []
        if view in ("sessions", "all"):
            items.extend(self.cache.get_sessions(f))
        if view in ("facilities", "all"):
            items.extend(self.cache.get_facilities(f))

        total = len(items)
        avail = sum(1 for x in items if (x.get("remaining") or 0) > 0)
        self.title_lbl.configure(text=view.capitalize() if view != "all" else "All")
        self.count_lbl.configure(text=f"{total} found  •  {avail} available")

        last = self.cache.last_updated
        ts = to_uk_local(last).strftime("%H:%M") if last else "—"
        watching_line = f"Watching: {len(self.watched)}\n" if self.watched else ""
        self.stats.configure(text=f"Sessions: {self.cache.sessions_count}\n"
                                  f"Facilities: {self.cache.facilities_count}\n"
                                  f"{watching_line}"
                                  f"Last sync: {ts}")

        self.vlist.set_items(items)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
