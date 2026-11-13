#!/usr/bin/env python3
"""
IISER Bhopal Captive Portal Manager - Desktop Application
Engineered to Apple macOS Human Interface Guidelines (HIG) standards:
- Modern macOS Source List Sidebar with clean grouped categories
- Inset Grouped Table Cards for Preferences with hairline dividers
- Clean vector status indicators with zero font/glyph dependencies
- Floating macOS HUD tooltips on hover across all options & controls
- Full keyboard ergonomics, real-time log stream, and network diagnostics
"""

import os
import sys

# Ensure backend and cli can be imported from app directory
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Intercept CLI subcommands immediately BEFORE importing Tkinter or CustomTkinter
# to enable 100% reliable execution in headless SSH or container environments.
if len(sys.argv) > 1 and sys.argv[1] not in ["--gui", "-g"]:
    import cli
    sys.exit(cli.handle_cli(sys.argv[1:]))

# Lazy load GUI modules
import threading
import time
import webbrowser
import subprocess
import tkinter as tk
import atexit
import tempfile
import fcntl
from typing import Optional, Tuple, Dict, Any

import customtkinter as ctk
import backend

try:
    import pystray
    from PIL import Image, ImageTk, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    try:
        from PIL import Image, ImageTk
    except ImportError:
        pass

# -----------------------------------------------------------------------------
# Apple macOS HIG Design Token System
# Dual-mode tuples: (Light Mode Hex, Dark Mode Hex)
# -----------------------------------------------------------------------------
APPLE_THEME = {
    # Canvas & Surface
    "window_bg": ("#F5F5F7", "#1E1E1E"),         # Off-white / Deep space gray
    "sidebar_bg": ("#ECECEC", "#252528"),        # macOS Source List backdrop
    "card_bg": ("#FFFFFF", "#2C2C2E"),           # Inset card surface
    "card_border": ("#E5E5EA", "#38383A"),       # 1px subtle hairline border
    "card_inner": ("#F9F9FB", "#323235"),        # Inner telemetry tile surface
    "divider": ("#EFEFF0", "#38383A"),           # Inset table row divider

    # Apple System Accents
    "accent_blue": ("#007AFF", "#0A84FF"),
    "accent_blue_hover": ("#0062CC", "#0071E3"),
    "accent_blue_subtle": ("#EBF5FF", "#0C2E52"),

    "accent_green": ("#34C759", "#30D158"),
    "accent_green_hover": ("#28A745", "#28C840"),
    "accent_green_subtle": ("#E8F8ED", "#0D331B"),

    "accent_red": ("#FF3B30", "#FF453A"),
    "accent_red_hover": ("#D70015", "#D32F2F"),
    "accent_red_subtle": ("#FDECEC", "#3D1414"),

    "accent_orange": ("#FF9500", "#FF9F0A"),
    "accent_orange_hover": ("#D97706", "#D97706"),
    "accent_orange_subtle": ("#FFF7EB", "#3D2B05"),

    # Tonal Secondary Controls
    "button_tonal_bg": ("#E8E8ED", "#3A3A3C"),
    "button_tonal_hover": ("#DCDCE2", "#48484A"),
    "button_tonal_text": ("#1D1D1F", "#F5F5F7"),

    # Typography Colors
    "text_primary": ("#1D1D1F", "#FFFFFF"),
    "text_secondary": ("#86868B", "#8E8E93"),
    "text_tertiary": ("#AEAEB2", "#636366"),

    # Input Fields
    "entry_bg": ("#FFFFFF", "#1C1C1E"),
    "entry_border": ("#D1D1D6", "#3A3A3C"),

    # Terminal / Console Log Background
    "console_bg": ("#18181A", "#121214"),
    "console_text": ("#E5E5EA", "#30D158"),

    # Corner Radii
    "radius_card": 12,
    "radius_button": 8,
    "radius_pill": 14,
    "radius_entry": 8,
    "radius_switch": 14,
}

# Typography Detection Cascade (San Francisco -> Helvetica Neue -> Ubuntu -> Cantarell)
BEST_FONT_FAMILY = "Helvetica"
BEST_MONO_FAMILY = "monospace"


def _detect_system_fonts():
    global BEST_FONT_FAMILY, BEST_MONO_FAMILY
    try:
        import tkinter.font as tkfont
        root_temp = ctk.CTk()
        root_temp.withdraw()
        known = [f.lower() for f in tkfont.families()]
        root_temp.destroy()

        candidates = [
            "SF Pro Display", "SF Pro Text", "SF Pro",
            "Helvetica Neue", "Helvetica", "Ubuntu",
            "Cantarell", "DejaVu Sans", "Arial"
        ]
        for cand in candidates:
            if cand.lower() in known:
                BEST_FONT_FAMILY = cand
                break

        mono_candidates = [
            "SF Mono", "Menlo", "Monaco", "Ubuntu Mono",
            "DejaVu Sans Mono", "courier", "monospace"
        ]
        for cand in mono_candidates:
            if cand.lower() in known:
                BEST_MONO_FAMILY = cand
                break
    except Exception:
        pass


_detect_system_fonts()


def get_macos_font(size: int = 13, weight: str = "normal", slant: str = "roman") -> ctk.CTkFont:
    """Return an Apple-inspired native typography token."""
    return ctk.CTkFont(family=BEST_FONT_FAMILY, size=size, weight=weight, slant=slant)


def get_macos_mono_font(size: int = 12) -> ctk.CTkFont:
    """Return an Apple Console monospaced typography token."""
    return ctk.CTkFont(family=BEST_MONO_FAMILY, size=size)


# Configure default appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# -----------------------------------------------------------------------------
# macOS Floating HUD Tooltip Implementation (Singleton Manager)
# -----------------------------------------------------------------------------
class TooltipManager:
    """
    Apple macOS HUD style floating tooltip manager (Singleton).
    Guarantees:
    1. Exactly ONE tooltip window can exist on the entire display at any time.
    2. Any existing tooltip is destroyed immediately when cursor moves or another element is scheduled.
    3. Tooltips dismiss immediately on click, scroll, window unmap, focus loss, or tab switch.
    4. Moving the cursor onto the tooltip window itself immediately destroys it.
    5. Tooltip will NEVER show if root window is not visible or mouse has moved outside the widget.
    6. All toplevels are cleaned up if the application is minimized, closed, or exited.
    """
    _instance: Optional["TooltipManager"] = None

    def __init__(self, root: tk.Tk):
        TooltipManager._instance = self
        self.root = root
        self._tip_window: Optional[tk.Toplevel] = None
        self._show_job: Optional[str] = None
        self._hide_job: Optional[str] = None
        self._current_widget = None
        self._current_text = ""

        # Global dismissal hooks on the root window
        self.root.bind_all("<ButtonPress>", lambda e: self.hide(), add="+")
        self.root.bind_all("<MouseWheel>", lambda e: self.hide(), add="+")
        self.root.bind_all("<Button-4>", lambda e: self.hide(), add="+")
        self.root.bind_all("<Button-5>", lambda e: self.hide(), add="+")
        self.root.bind_all("<Key>", lambda e: self.hide(), add="+")
        self.root.bind("<Unmap>", lambda e: self.hide(), add="+")
        self.root.bind("<FocusOut>", lambda e: self.hide(), add="+")

    @classmethod
    def get_instance(cls, root: Optional[tk.Tk] = None) -> Optional["TooltipManager"]:
        if cls._instance is not None:
            return cls._instance
        if root is not None:
            return cls(root)
        return None

    def hide(self):
        """Immediately cancel pending timers and destroy any floating tooltip window."""
        self._cancel_show()
        self._cancel_hide()
        self._current_widget = None
        self._current_text = ""
        if self._tip_window:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None

    def _cancel_show(self):
        if self._show_job:
            try:
                self.root.after_cancel(self._show_job)
            except Exception:
                pass
            self._show_job = None

    def _cancel_hide(self):
        if self._hide_job:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None

    def register(self, widget, text: str, delay: int = 400):
        """Attach tooltip text to a widget and its child elements."""
        def on_enter(event=None):
            self._cancel_hide()
            # If pointer is within the same widget and it's already showing, keep it
            if self._current_widget is widget and self._tip_window:
                return

            # Switching to another widget: kill existing tooltip immediately
            if self._current_widget is not widget:
                self.hide()

            self._current_widget = widget
            self._current_text = text
            self._cancel_show()
            self._show_job = self.root.after(delay, lambda: self._show(widget, text))

        def on_leave(event=None):
            self._cancel_show()
            self._cancel_hide()
            # 80ms debounce so crossing internal CTk widget boundaries doesn't flicker
            self._hide_job = self.root.after(80, self._on_delayed_leave)

        def bind_tree(target):
            try:
                target.bind("<Enter>", on_enter, add="+")
                target.bind("<Leave>", on_leave, add="+")
            except Exception:
                pass
            try:
                for child in target.winfo_children():
                    bind_tree(child)
            except Exception:
                pass

        bind_tree(widget)

    def _on_delayed_leave(self):
        self._hide_job = None
        self.hide()

    def _show(self, widget, text: str):
        self._show_job = None

        # Verify target is still this widget and widget still exists
        if self._current_widget is not widget or not widget.winfo_exists():
            self.hide()
            return

        try:
            if not self.root.winfo_viewable():
                self.hide()
                return
        except Exception:
            self.hide()
            return

        # Verify pointer is actually inside the widget boundaries right now
        try:
            px = self.root.winfo_pointerx()
            py = self.root.winfo_pointery()
            wx = widget.winfo_rootx()
            wy = widget.winfo_rooty()
            ww = widget.winfo_width()
            wh = widget.winfo_height()
            if not (wx - 2 <= px <= wx + ww + 2 and wy - 2 <= py <= wy + wh + 2):
                self.hide()
                return
        except Exception:
            return

        # Destroy any existing tooltip window first
        if self._tip_window:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None

        x = px + 12
        y = py + 18

        self._tip_window = tw = tk.Toplevel(self.root)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-type", "tooltip")
        except Exception:
            pass
        try:
            tw.wm_attributes("-topmost", True)
        except Exception:
            pass

        # CRITICAL: If pointer enters or clicks the tooltip itself, dismiss immediately!
        tw.bind("<Enter>", lambda e: self.hide())
        tw.bind("<ButtonPress>", lambda e: self.hide())

        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_col = "#2C2C2E" if is_dark else "#FFFFFF"
        border_col = "#48484A" if is_dark else "#D1D1D6"
        text_col = "#FFFFFF" if is_dark else "#1D1D1F"

        tw.configure(bg=bg_col)

        frame = ctk.CTkFrame(
            tw, corner_radius=8,
            border_width=1,
            border_color=border_col,
            fg_color=bg_col
        )
        frame.pack()
        frame.bind("<Enter>", lambda e: self.hide())
        frame.bind("<ButtonPress>", lambda e: self.hide())

        lbl = ctk.CTkLabel(
            frame, text=text,
            font=get_macos_font(size=11),
            text_color=text_col,
            wraplength=280, justify="left",
            padx=10, pady=6
        )
        lbl.pack()
        lbl.bind("<Enter>", lambda e: self.hide())
        lbl.bind("<ButtonPress>", lambda e: self.hide())

        tw.update_idletasks()
        w = tw.winfo_reqwidth()
        h = tw.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # Display edge clamping
        if x + w > sw - 12:
            x = max(10, px - w - 10)
        if y + h > sh - 12:
            y = max(10, py - h - 10)
        if x < 10:
            x = 10
        if y < 10:
            y = 10

        tw.geometry(f"+{x}+{y}")


def _cleanup_tooltips():
    if TooltipManager._instance:
        TooltipManager._instance.hide()


atexit.register(_cleanup_tooltips)


def add_tooltip(widget, text: str, delay: int = 400):
    """Helper to attach a floating macOS tooltip to any widget using TooltipManager."""
    try:
        mgr = TooltipManager.get_instance()
        if not mgr:
            try:
                root = widget.winfo_toplevel()
                mgr = TooltipManager.get_instance(root)
            except Exception:
                mgr = None
        if mgr:
            mgr.register(widget, text, delay=delay)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Main Application Window
# -----------------------------------------------------------------------------
class IISERBLoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("IISERB Portal - Captive Network Manager")
        self.minsize(760, 500)
        self.configure(fg_color=APPLE_THEME["window_bg"])

        # Optical screen centering
        self._center_window(940, 630)

        # Multi-resolution Retina icon loading
        self.icon_path = os.path.join(APP_DIR, "icon.png")
        self._icon_photos = []
        self._set_crisp_icons()

        # State tracking
        self.current_tab = "status"
        self.is_checking_network = False
        self.log_auto_refresh = True
        self.last_log_content = ""
        self.tray_icon = None

        # Root Layout: 2 Columns (Sidebar & Main Surface)
        self.grid_columnconfigure(0, weight=0, minsize=230)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Centralized Tooltip Manager singleton
        self.tooltip_manager = TooltipManager(self)

        self._create_sidebar()
        self._create_main_content()

        # Unified keyboard ergonomics
        self._register_keyboard_shortcuts()

        # Window close handler (minimize to tray if available)
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # System tray setup
        if TRAY_AVAILABLE and os.path.exists(self.icon_path):
            self._setup_tray_icon()

        # Background monitoring loop
        self._start_periodic_monitoring()

    def _center_window(self, width: int = 940, height: int = 630):
        try:
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 2 - 30)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self.geometry(f"{width}x{height}")

    def _set_crisp_icons(self):
        if os.path.exists(self.icon_path):
            try:
                base_img = Image.open(self.icon_path)
                for s in [16, 24, 32, 48, 64, 128, 256]:
                    resized = base_img.resize((s, s), Image.Resampling.LANCZOS)
                    self._icon_photos.append(ImageTk.PhotoImage(resized))
                self.iconphoto(False, *self._icon_photos)
            except Exception:
                pass

    def _register_keyboard_shortcuts(self):
        for k in ["<Control-r>", "<Control-R>", "<Command-r>", "<Command-R>", "<F5>"]:
            self.bind_all(k, lambda e: self.refresh_all_status())

        for k in ["<Control-l>", "<Control-L>", "<Command-l>", "<Command-L>"]:
            self.bind_all(k, lambda e: self._handle_manual_login())

        tab_map = {"1": "status", "2": "logs", "3": "diag", "4": "settings"}
        for num, tab_name in tab_map.items():
            for mod in ["Control", "Command"]:
                self.bind_all(f"<{mod}-Key-{num}>", lambda e, t=tab_name: self._select_tab(t))

        for mod in ["Control", "Command"]:
            self.bind_all(f"<{mod}-comma>", lambda e: self._select_tab("settings"))

        self.bind_all("<Escape>", lambda e: self._handle_escape_press())

    def _handle_escape_press(self):
        self.focus_set()
        if hasattr(self, "lbl_action_msg"):
            self.lbl_action_msg.configure(text="")
        if hasattr(self, "lbl_settings_alert"):
            self.lbl_settings_alert.configure(text="")

    # =========================================================================
    # SIDEBAR: macOS Source List Navigation
    # =========================================================================
    def _create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(
            self, width=230, corner_radius=0,
            fg_color=APPLE_THEME["sidebar_bg"]
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)

        # 1. App Identity Header
        brand_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        brand_frame.pack(fill="x", padx=18, pady=(20, 14))

        app_title = ctk.CTkLabel(
            brand_frame, text="IISERB Portal",
            font=get_macos_font(size=17, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        )
        app_title.pack(anchor="w")

        app_subtitle = ctk.CTkLabel(
            brand_frame, text="Network Auto-Login",
            font=get_macos_font(size=11),
            text_color=APPLE_THEME["text_secondary"]
        )
        app_subtitle.pack(anchor="w", pady=(1, 0))

        # 2. Sidebar Live Connection Capsule with Vector Dot
        self.pill_sidebar_status = ctk.CTkFrame(
            self.sidebar_frame, corner_radius=12,
            fg_color=APPLE_THEME["card_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        self.pill_sidebar_status.pack(fill="x", padx=14, pady=(0, 18))
        add_tooltip(self.pill_sidebar_status, "Real-time network connection health indicator.")

        dot_box = ctk.CTkFrame(self.pill_sidebar_status, fg_color="transparent")
        dot_box.pack(side="left", padx=(10, 4), pady=6)

        self.dot_sidebar = ctk.CTkFrame(
            dot_box, width=8, height=8, corner_radius=4,
            fg_color=APPLE_THEME["accent_orange"]
        )
        self.dot_sidebar.pack(side="left")

        self.lbl_sidebar_status_text = ctk.CTkLabel(
            self.pill_sidebar_status, text="Checking status...",
            font=get_macos_font(size=11, weight="bold"),
            text_color=APPLE_THEME["text_secondary"]
        )
        self.lbl_sidebar_status_text.pack(side="left", padx=(0, 10), pady=6)

        # 3. Navigation Group 1: MAIN
        lbl_sec_main = ctk.CTkLabel(
            self.sidebar_frame, text="MAIN",
            font=get_macos_font(size=10, weight="bold"),
            text_color=APPLE_THEME["text_tertiary"]
        )
        lbl_sec_main.pack(anchor="w", padx=18, pady=(4, 4))

        self.btn_nav_status = self._create_nav_pill("Dashboard", "status")
        self.btn_nav_status.pack(fill="x", padx=10, pady=2)
        add_tooltip(self.btn_nav_status, "View real-time connection status, telemetry gauges, and quick action controls.")

        self.btn_nav_logs = self._create_nav_pill("Live Console", "logs")
        self.btn_nav_logs.pack(fill="x", padx=10, pady=2)
        add_tooltip(self.btn_nav_logs, "Monitor live authentication logs, keepalive pulses, and systemd service events.")

        self.btn_nav_diag = self._create_nav_pill("Network Doctor", "diag")
        self.btn_nav_diag.pack(fill="x", padx=10, pady=2)
        add_tooltip(self.btn_nav_diag, "Run automated network reachability and captive portal diagnostics.")

        # 4. Navigation Group 2: CONFIGURATION
        lbl_sec_cfg = ctk.CTkLabel(
            self.sidebar_frame, text="CONFIGURATION",
            font=get_macos_font(size=10, weight="bold"),
            text_color=APPLE_THEME["text_tertiary"]
        )
        lbl_sec_cfg.pack(anchor="w", padx=18, pady=(18, 4))

        self.btn_nav_settings = self._create_nav_pill("Preferences", "settings")
        self.btn_nav_settings.pack(fill="x", padx=10, pady=2)
        add_tooltip(self.btn_nav_settings, "Configure LDAP credentials, ping intervals, gateway URLs, and automation settings.")

        # Spacer pushes appearance menu to bottom
        spacer = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # 5. Sidebar Footer: macOS Segmented Theme Switcher
        theme_box = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        theme_box.pack(fill="x", padx=14, pady=(0, 18))

        lbl_theme = ctk.CTkLabel(
            theme_box, text="APPEARANCE",
            font=get_macos_font(size=10, weight="bold"),
            text_color=APPLE_THEME["text_tertiary"]
        )
        lbl_theme.pack(anchor="w", padx=4, pady=(0, 6))

        self.seg_theme = ctk.CTkSegmentedButton(
            theme_box, values=["Dark", "Light", "System"],
            corner_radius=APPLE_THEME["radius_button"],
            font=get_macos_font(size=11),
            height=28, command=self._change_appearance_mode
        )
        self.seg_theme.pack(fill="x")
        self.seg_theme.set("Dark")
        add_tooltip(self.seg_theme, "Toggle between Dark mode, Light mode, or follow the system appearance.")

    def _create_nav_pill(self, label: str, tab_id: str) -> ctk.CTkButton:
        return ctk.CTkButton(
            self.sidebar_frame, text=f"  {label}",
            command=lambda: self._select_tab(tab_id),
            anchor="w", height=34,
            corner_radius=APPLE_THEME["radius_button"],
            font=get_macos_font(size=13),
            fg_color="transparent",
            text_color=APPLE_THEME["text_primary"],
            hover_color=("#E2E2E6", "#2E2E32")
        )

    # =========================================================================
    # MAIN CONTENT CONTAINER & TABS
    # =========================================================================
    def _create_main_content(self):
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=16)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        self.tab_status = self._build_status_tab()
        self.tab_settings = self._build_settings_tab()
        self.tab_logs = self._build_logs_tab()
        self.tab_diag = self._build_diag_tab()

        self._select_tab("status")

    # -------------------------------------------------------------------------
    # TAB 1: DASHBOARD (Hero Connection & Telemetry)
    # -------------------------------------------------------------------------
    def _build_status_tab(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(
            self.content_container, fg_color="transparent",
            scrollbar_fg_color="transparent",
            scrollbar_button_color=APPLE_THEME["button_tonal_bg"],
            scrollbar_button_hover_color=APPLE_THEME["button_tonal_hover"]
        )
        frame._scrollbar.configure(width=8)

        # 0. Onboarding Card (Conditional)
        self.card_onboarding = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["accent_blue_subtle"],
            border_width=1, border_color=APPLE_THEME["accent_blue"]
        )
        onboard_box = ctk.CTkFrame(self.card_onboarding, fg_color="transparent")
        onboard_box.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            onboard_box,
            text="Welcome to IISERB Login. Configure your LDAP roll number and password in Preferences to enable auto-login.",
            font=get_macos_font(size=12, weight="bold"),
            text_color=APPLE_THEME["accent_blue"]
        ).pack(side="left", padx=(0, 15), fill="x", expand=True)

        ctk.CTkButton(
            onboard_box, text="Open Preferences", width=130, height=30,
            corner_radius=APPLE_THEME["radius_button"],
            fg_color=APPLE_THEME["accent_blue"],
            hover_color=APPLE_THEME["accent_blue_hover"],
            font=get_macos_font(size=12, weight="bold"),
            command=lambda: self._select_tab("settings")
        ).pack(side="right")

        cfg = backend.load_config()
        if not cfg.get("USERNAME") or not cfg.get("PASSWORD"):
            self.card_onboarding.pack(fill="x", pady=(0, 14))

        # 1. HERO CONNECTION STATUS CARD
        self.card_hero = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["card_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        self.card_hero.pack(fill="x", pady=(0, 14))
        add_tooltip(self.card_hero, "Shows your current campus network connectivity and gateway authentication state.")

        hero_top = ctk.CTkFrame(self.card_hero, fg_color="transparent")
        hero_top.pack(fill="x", padx=20, pady=(18, 12))

        # Hero Vector Status Dot
        dot_wrapper = ctk.CTkFrame(hero_top, fg_color="transparent")
        dot_wrapper.pack(side="left", padx=(0, 14))

        self.hero_dot = ctk.CTkFrame(
            dot_wrapper, width=12, height=12, corner_radius=6,
            fg_color=APPLE_THEME["accent_orange"]
        )
        self.hero_dot.pack(side="left", pady=4)

        hero_info = ctk.CTkFrame(hero_top, fg_color="transparent")
        hero_info.pack(side="left", fill="x", expand=True)

        self.lbl_hero_title = ctk.CTkLabel(
            hero_info, text="Checking Connectivity...",
            font=get_macos_font(size=18, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        )
        self.lbl_hero_title.pack(anchor="w")

        self.lbl_hero_sub = ctk.CTkLabel(
            hero_info, text="Inspecting FortiGate captive gateway and DNS route...",
            font=get_macos_font(size=12),
            text_color=APPLE_THEME["text_secondary"]
        )
        self.lbl_hero_sub.pack(anchor="w", pady=(2, 0))

        # Top Right Hero Status Badge
        self.badge_status = ctk.CTkButton(
            hero_top, text="CHECKING",
            fg_color=APPLE_THEME["accent_orange_subtle"],
            text_color=APPLE_THEME["accent_orange"],
            font=get_macos_font(size=12, weight="bold"),
            corner_radius=APPLE_THEME["radius_pill"],
            height=30, hover=False
        )
        self.badge_status.pack(side="right")
        add_tooltip(self.badge_status, "Current authorization status with the campus firewall.")

        # 4-Pill Inset Telemetry Bar
        telemetry_bar = ctk.CTkFrame(self.card_hero, fg_color="transparent")
        telemetry_bar.pack(fill="x", padx=20, pady=(0, 16))
        telemetry_bar.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="pill")

        self.tile_latency = self._create_telemetry_tile(telemetry_bar, 0, "LATENCY", "-- ms")
        add_tooltip(self.tile_latency, "Round-trip network latency to the ping target (1.1.1.1).")

        self.tile_ip = self._create_telemetry_tile(telemetry_bar, 1, "LOCAL IP", "Resolving...")
        add_tooltip(self.tile_ip, "Current IPv4 address assigned to your machine by campus DHCP.")

        self.tile_dev = self._create_telemetry_tile(telemetry_bar, 2, "INTERFACE", "--")
        add_tooltip(self.tile_dev, "Active hardware network adapter used for campus connectivity.")

        self.tile_gw = self._create_telemetry_tile(telemetry_bar, 3, "GATEWAY", "--")
        add_tooltip(self.tile_gw, "Default network gateway IP routing your traffic to the IISERB firewall.")

        # 1px Inset Divider
        divider1 = ctk.CTkFrame(self.card_hero, height=1, fg_color=APPLE_THEME["divider"])
        divider1.pack(fill="x", padx=20, pady=(0, 14))

        # Quick Actions Row
        action_row = ctk.CTkFrame(self.card_hero, fg_color="transparent")
        action_row.pack(fill="x", padx=20, pady=(0, 12))

        # Primary Apple Accent Blue Action Button
        self.btn_manual_login = ctk.CTkButton(
            action_row, text="Force Login Now",
            font=get_macos_font(size=13, weight="bold"),
            fg_color=APPLE_THEME["accent_blue"],
            hover_color=APPLE_THEME["accent_blue_hover"],
            corner_radius=APPLE_THEME["radius_button"],
            height=36, command=self._handle_manual_login
        )
        self.btn_manual_login.pack(side="left", expand=True, fill="x", padx=(0, 8))
        add_tooltip(self.btn_manual_login, "Submit your saved LDAP credentials to the FortiGate gateway immediately.")

        # Secondary Tonal Action Buttons
        self.btn_refresh = self._create_tonal_btn(action_row, "Check Now", self.refresh_all_status)
        self.btn_refresh.pack(side="left", padx=(0, 8))
        add_tooltip(self.btn_refresh, "Perform an instant internet reachability and latency probe.")

        self.btn_reconnect_lan = self._create_tonal_btn(action_row, "Reset Link", self._handle_reconnect_lan)
        self.btn_reconnect_lan.pack(side="left", padx=(0, 8))
        add_tooltip(self.btn_reconnect_lan, "Non-destructively flushes ARP cache and link state without dropping active SSH sessions.")

        self.btn_hard_restart = self._create_tonal_btn(action_row, "Hard LAN Reset", self._handle_hard_restart_lan)
        self.btn_hard_restart.pack(side="left", padx=(0, 8))
        add_tooltip(self.btn_hard_restart, "Schedules an automatic 10-second reconnect timer before cycling the physical Ethernet link.")

        self.btn_open_portal = self._create_tonal_btn(action_row, "Open Portal", self._open_portal_browser)
        self.btn_open_portal.pack(side="left", padx=(0, 8))
        add_tooltip(self.btn_open_portal, "Opens the captive portal HTTP login page in your default web browser.")

        self.btn_logout = self._create_tonal_btn(action_row, "Logout", self._handle_logout)
        self.btn_logout.pack(side="left")
        add_tooltip(self.btn_logout, "Terminates the active authenticated session with the campus gateway.")

        # Action status notification label
        self.lbl_action_msg = ctk.CTkLabel(
            self.card_hero, text="", font=get_macos_font(size=12),
            text_color=APPLE_THEME["text_secondary"]
        )
        self.lbl_action_msg.pack(anchor="w", padx=20, pady=(0, 14))

        # 2. BACKGROUND DAEMON KEEPALIVE CARD
        card_service = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["card_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        card_service.pack(fill="x", pady=(0, 14))
        add_tooltip(card_service, "Controls the background systemd keepalive daemon (portal-autologin.service).")

        svc_header = ctk.CTkFrame(card_service, fg_color="transparent")
        svc_header.pack(fill="x", padx=20, pady=(16, 12))

        ctk.CTkLabel(
            svc_header, text="Background Keepalive Service",
            font=get_macos_font(size=15, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        ).pack(side="left")

        self.lbl_svc_capsule = ctk.CTkLabel(
            svc_header, text="Checking...",
            font=get_macos_font(size=12, weight="bold"),
            fg_color=APPLE_THEME["button_tonal_bg"],
            text_color=APPLE_THEME["text_secondary"],
            corner_radius=APPLE_THEME["radius_pill"],
            height=26, padx=10
        )
        self.lbl_svc_capsule.pack(side="right")
        add_tooltip(self.lbl_svc_capsule, "Live operational status of the user systemd background unit.")

        svc_body = ctk.CTkFrame(card_service, fg_color="transparent")
        svc_body.pack(fill="x", padx=20, pady=(0, 16))
        svc_body.grid_columnconfigure(0, weight=1)
        svc_body.grid_columnconfigure(1, weight=1)

        # Autostart Switch
        svc_sw_box = ctk.CTkFrame(svc_body, fg_color="transparent")
        svc_sw_box.grid(row=0, column=0, sticky="w")

        self.switch_autostart = ctk.CTkSwitch(
            svc_sw_box, text="Start on System Boot",
            command=self._toggle_autostart,
            font=get_macos_font(size=13),
            progress_color=APPLE_THEME["accent_green"][0],
            button_color="#FFFFFF",
            fg_color=("#D1D1D6", "#3A3A3C")
        )
        self.switch_autostart.pack(anchor="w")
        add_tooltip(self.switch_autostart, "Enable or disable automatic background authentication on system startup.")

        ctk.CTkLabel(
            svc_sw_box, text="Manages user systemd unit portal-autologin.service",
            font=get_macos_font(size=11), text_color=APPLE_THEME["text_secondary"]
        ).pack(anchor="w", pady=(4, 0))

        # Service Action Controls
        svc_btn_box = ctk.CTkFrame(svc_body, fg_color="transparent")
        svc_btn_box.grid(row=0, column=1, sticky="e")

        self.btn_svc_start = self._create_tonal_btn(svc_btn_box, "Start", lambda: self._handle_service_action("start"))
        self.btn_svc_start.pack(side="left", padx=(0, 6))
        add_tooltip(self.btn_svc_start, "Start the background keepalive daemon immediately.")

        self.btn_svc_stop = self._create_tonal_btn(svc_btn_box, "Stop", lambda: self._handle_service_action("stop"))
        self.btn_svc_stop.pack(side="left", padx=(0, 6))
        add_tooltip(self.btn_svc_stop, "Stop the background keepalive daemon.")

        self.btn_svc_restart = self._create_tonal_btn(svc_btn_box, "Restart", lambda: self._handle_service_action("restart"))
        self.btn_svc_restart.pack(side="left")
        add_tooltip(self.btn_svc_restart, "Restart the background daemon to apply any configuration changes.")

        return frame

    def _create_telemetry_tile(self, parent, col: int, label: str, init_val: str):
        tile = ctk.CTkFrame(
            parent, corner_radius=APPLE_THEME["radius_button"],
            fg_color=APPLE_THEME["card_inner"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        tile.grid(row=0, column=col, padx=4, sticky="nsew")

        ctk.CTkLabel(
            tile, text=label, font=get_macos_font(size=10, weight="bold"),
            text_color=APPLE_THEME["text_tertiary"]
        ).pack(anchor="w", padx=10, pady=(8, 2))

        val_label = ctk.CTkLabel(
            tile, text=init_val, font=get_macos_font(size=13, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        )
        val_label.pack(anchor="w", padx=10, pady=(0, 8))
        return val_label

    def _create_tonal_btn(self, parent, text: str, cmd):
        return ctk.CTkButton(
            parent, text=text, command=cmd,
            font=get_macos_font(size=12),
            fg_color=APPLE_THEME["button_tonal_bg"],
            hover_color=APPLE_THEME["button_tonal_hover"],
            text_color=APPLE_THEME["button_tonal_text"],
            corner_radius=APPLE_THEME["radius_button"],
            height=36
        )

    # -------------------------------------------------------------------------
    # TAB 2: PREFERENCES (macOS Inset Grouped Table Cards)
    # -------------------------------------------------------------------------
    def _build_settings_tab(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(
            self.content_container, fg_color="transparent",
            scrollbar_fg_color="transparent",
            scrollbar_button_color=APPLE_THEME["button_tonal_bg"],
            scrollbar_button_hover_color=APPLE_THEME["button_tonal_hover"]
        )
        frame._scrollbar.configure(width=8)

        # CARD 1: USER ACCOUNT & CREDENTIALS
        card_creds = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["card_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        card_creds.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            card_creds, text="Account and LDAP Credentials",
            font=get_macos_font(size=15, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        ).pack(anchor="w", padx=20, pady=(16, 12))

        # Row 1: Username
        row_user = ctk.CTkFrame(card_creds, fg_color="transparent")
        row_user.pack(fill="x", padx=20, pady=(0, 10))
        row_user.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_user, text="Username (LDAP):", font=get_macos_font(size=13),
            text_color=APPLE_THEME["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.entry_username = ctk.CTkEntry(
            row_user, height=34, corner_radius=APPLE_THEME["radius_entry"],
            placeholder_text="e.g. rollnumber",
            font=get_macos_font(size=13),
            fg_color=APPLE_THEME["entry_bg"],
            border_color=APPLE_THEME["entry_border"]
        )
        self.entry_username.grid(row=0, column=1, sticky="ew")
        self.entry_username.bind("<Return>", lambda e: self.entry_password.focus_set())
        add_tooltip(self.entry_username, "Your IISER Bhopal LDAP login ID (e.g. your roll number).")

        # Row 2: Divider
        ctk.CTkFrame(card_creds, height=1, fg_color=APPLE_THEME["divider"]).pack(fill="x", padx=20, pady=(0, 10))

        # Row 3: Password
        row_pass = ctk.CTkFrame(card_creds, fg_color="transparent")
        row_pass.pack(fill="x", padx=20, pady=(0, 16))
        row_pass.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_pass, text="Password:", font=get_macos_font(size=13),
            text_color=APPLE_THEME["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        pass_inner = ctk.CTkFrame(row_pass, fg_color="transparent")
        pass_inner.grid(row=0, column=1, sticky="ew")
        pass_inner.grid_columnconfigure(0, weight=1)

        self.entry_password = ctk.CTkEntry(
            pass_inner, show="*", height=34,
            corner_radius=APPLE_THEME["radius_entry"],
            placeholder_text="LDAP password",
            font=get_macos_font(size=13),
            fg_color=APPLE_THEME["entry_bg"],
            border_color=APPLE_THEME["entry_border"]
        )
        self.entry_password.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry_password.bind("<Return>", self._handle_password_enter)
        add_tooltip(self.entry_password, "Your LDAP network authentication password (stored securely with 0600 file permissions).")

        self.chk_show_pass = ctk.CTkCheckBox(
            pass_inner, text="Show", width=60, command=self._toggle_password_visibility,
            font=get_macos_font(size=12)
        )
        self.chk_show_pass.grid(row=0, column=1)
        add_tooltip(self.chk_show_pass, "Toggle visibility of the password characters.")

        # CARD 2: NETWORK & KEEPALIVE TIMING
        card_opts = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["card_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        card_opts.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            card_opts, text="Connection and Timing Parameters",
            font=get_macos_font(size=15, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        ).pack(anchor="w", padx=20, pady=(16, 12))

        # Ping Target
        row_ping = ctk.CTkFrame(card_opts, fg_color="transparent")
        row_ping.pack(fill="x", padx=20, pady=(0, 10))
        row_ping.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_ping, text="Ping Target (DNS):", font=get_macos_font(size=13),
            text_color=APPLE_THEME["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.entry_ping_target = ctk.CTkEntry(
            row_ping, height=34, corner_radius=APPLE_THEME["radius_entry"],
            font=get_macos_font(size=13),
            fg_color=APPLE_THEME["entry_bg"], border_color=APPLE_THEME["entry_border"]
        )
        self.entry_ping_target.grid(row=0, column=1, sticky="ew")
        add_tooltip(self.entry_ping_target, "External IP or DNS host (default: 1.1.1.1) used to verify internet connectivity.")

        # Divider
        ctk.CTkFrame(card_opts, height=1, fg_color=APPLE_THEME["divider"]).pack(fill="x", padx=20, pady=(0, 10))

        # Check Interval
        row_int = ctk.CTkFrame(card_opts, fg_color="transparent")
        row_int.pack(fill="x", padx=20, pady=(0, 10))
        row_int.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_int, text="Check Interval (sec):", font=get_macos_font(size=13),
            text_color=APPLE_THEME["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        int_box = ctk.CTkFrame(row_int, fg_color="transparent")
        int_box.grid(row=0, column=1, sticky="ew")
        int_box.grid_columnconfigure(0, weight=1)

        self.slider_interval = ctk.CTkSlider(
            int_box, from_=10, to=300, number_of_steps=29, command=self._update_slider_label,
            progress_color=APPLE_THEME["accent_blue"][0]
        )
        self.slider_interval.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        add_tooltip(self.slider_interval, "Frequency in seconds between background connection health checks.")

        self.lbl_slider_val = ctk.CTkLabel(
            int_box, text="60s", width=55, font=get_macos_font(size=12, weight="bold")
        )
        self.lbl_slider_val.grid(row=0, column=1)

        # Divider
        ctk.CTkFrame(card_opts, height=1, fg_color=APPLE_THEME["divider"]).pack(fill="x", padx=20, pady=(0, 10))

        # Keepalive Interval
        row_ka = ctk.CTkFrame(card_opts, fg_color="transparent")
        row_ka.pack(fill="x", padx=20, pady=(0, 10))
        row_ka.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_ka, text="Keepalive Ping (min):", font=get_macos_font(size=13),
            text_color=APPLE_THEME["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        ka_box = ctk.CTkFrame(row_ka, fg_color="transparent")
        ka_box.grid(row=0, column=1, sticky="ew")
        ka_box.grid_columnconfigure(0, weight=1)

        self.slider_ka = ctk.CTkSlider(
            ka_box, from_=1, to=30, number_of_steps=29, command=self._update_ka_label,
            progress_color=APPLE_THEME["accent_blue"][0]
        )
        self.slider_ka.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        add_tooltip(self.slider_ka, "Interval in minutes between HTTP keepalive pulses sent to the gateway.")

        self.lbl_ka_val = ctk.CTkLabel(
            ka_box, text="3 min", width=55, font=get_macos_font(size=12, weight="bold")
        )
        self.lbl_ka_val.grid(row=0, column=1)

        # Divider
        ctk.CTkFrame(card_opts, height=1, fg_color=APPLE_THEME["divider"]).pack(fill="x", padx=20, pady=(0, 10))

        # Gateway URL
        row_gw = ctk.CTkFrame(card_opts, fg_color="transparent")
        row_gw.pack(fill="x", padx=20, pady=(0, 10))
        row_gw.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_gw, text="Gateway URL:", font=get_macos_font(size=13),
            text_color=APPLE_THEME["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.entry_gateway = ctk.CTkEntry(
            row_gw, height=34, corner_radius=APPLE_THEME["radius_entry"],
            font=get_macos_font(size=13),
            fg_color=APPLE_THEME["entry_bg"], border_color=APPLE_THEME["entry_border"]
        )
        self.entry_gateway.grid(row=0, column=1, sticky="ew")
        add_tooltip(self.entry_gateway, "URL of the FortiGate captive portal authentication gateway.")

        # Divider
        ctk.CTkFrame(card_opts, height=1, fg_color=APPLE_THEME["divider"]).pack(fill="x", padx=20, pady=(0, 10))

        # Probe URL
        row_probe = ctk.CTkFrame(card_opts, fg_color="transparent")
        row_probe.pack(fill="x", padx=20, pady=(0, 16))
        row_probe.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_probe, text="Probe Target:", font=get_macos_font(size=13),
            text_color=APPLE_THEME["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.combo_probe = ctk.CTkComboBox(
            row_probe, height=34, corner_radius=APPLE_THEME["radius_entry"],
            font=get_macos_font(size=13),
            values=[
                "http://connectivity-check.ubuntu.com/",
                "http://clients3.google.com/generate_204",
                "http://detectportal.firefox.com/success.txt",
                "http://neverssl.com"
            ]
        )
        self.combo_probe.grid(row=0, column=1, sticky="ew")
        add_tooltip(self.combo_probe, "HTTP endpoint used to detect captive portal redirection.")

        # CARD 3: AUTOMATION & RESILIENCY
        card_auto = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["card_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        card_auto.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            card_auto, text="Resiliency and Desktop Alerts",
            font=get_macos_font(size=15, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        ).pack(anchor="w", padx=20, pady=(16, 12))

        # Desktop Alerts Switch
        row_notif = ctk.CTkFrame(card_auto, fg_color="transparent")
        row_notif.pack(fill="x", padx=20, pady=(0, 12))

        self.switch_notifications = ctk.CTkSwitch(
            row_notif, text="Send native desktop notifications on status change",
            font=get_macos_font(size=13),
            progress_color=APPLE_THEME["accent_green"][0],
            button_color="#FFFFFF",
            fg_color=("#D1D1D6", "#3A3A3C")
        )
        self.switch_notifications.pack(anchor="w")
        add_tooltip(self.switch_notifications, "Display native desktop notifications on login success, failure, or network changes.")

        # Divider
        ctk.CTkFrame(card_auto, height=1, fg_color=APPLE_THEME["divider"]).pack(fill="x", padx=20, pady=(0, 10))

        # Auto Hard Bounce Switch
        row_hard = ctk.CTkFrame(card_auto, fg_color="transparent")
        row_hard.pack(fill="x", padx=20, pady=(0, 16))

        self.switch_auto_hard = ctk.CTkSwitch(
            row_hard, text="Auto SSH-safe hard LAN bounce if gateway challenge stalls",
            font=get_macos_font(size=13),
            progress_color=APPLE_THEME["accent_green"][0],
            button_color="#FFFFFF",
            fg_color=("#D1D1D6", "#3A3A3C")
        )
        self.switch_auto_hard.pack(anchor="w")
        add_tooltip(self.switch_auto_hard, "Automatically perform an SSH-safe hard LAN restart if the captive challenge stalls.")

        # Floating Bottom Action Bar
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 16))

        self.btn_save_settings = ctk.CTkButton(
            btn_row, text="Save Settings", height=38,
            font=get_macos_font(size=13, weight="bold"),
            fg_color=APPLE_THEME["accent_blue"],
            hover_color=APPLE_THEME["accent_blue_hover"],
            corner_radius=APPLE_THEME["radius_button"],
            command=self._save_settings
        )
        self.btn_save_settings.pack(side="left", padx=(0, 10))
        add_tooltip(self.btn_save_settings, "Save all settings to ~/.config/iiserb_login/config.json and reload the background service.")

        self.btn_reset_defaults = self._create_tonal_btn(
            btn_row, "Reset Defaults", self._load_defaults_into_ui
        )
        self.btn_reset_defaults.pack(side="left")
        add_tooltip(self.btn_reset_defaults, "Restore all settings fields to recommended factory defaults.")

        self.lbl_settings_alert = ctk.CTkLabel(
            btn_row, text="", font=get_macos_font(size=12)
        )
        self.lbl_settings_alert.pack(side="left", padx=(16, 0))

        # Pre-populate settings from disk
        self._load_saved_settings_into_ui()

        return frame

    # -------------------------------------------------------------------------
    # TAB 3: LIVE CONSOLE (Clean Stream View)
    # -------------------------------------------------------------------------
    def _build_logs_tab(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content_container, fg_color="transparent")

        top_bar = ctk.CTkFrame(frame, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 12))

        lbl_head = ctk.CTkLabel(
            top_bar, text="Console Stream",
            font=get_macos_font(size=16, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        )
        lbl_head.pack(side="left", padx=(0, 14))

        # Real-time search filter box
        self.entry_filter_logs = ctk.CTkEntry(
            top_bar, placeholder_text="Filter log entries...",
            width=210, height=28, corner_radius=APPLE_THEME["radius_pill"],
            font=get_macos_font(size=12),
            fg_color=APPLE_THEME["entry_bg"], border_color=APPLE_THEME["entry_border"]
        )
        self.entry_filter_logs.pack(side="left")
        self.entry_filter_logs.bind("<KeyRelease>", lambda e: self._filter_logs())
        add_tooltip(self.entry_filter_logs, "Filter visible log entries in real time by typing keywords.")

        # Auto-refresh switch
        self.chk_auto_scroll = ctk.CTkSwitch(
            top_bar, text="Auto-refresh", command=self._toggle_auto_scroll,
            font=get_macos_font(size=12),
            progress_color=APPLE_THEME["accent_green"][0]
        )
        self.chk_auto_scroll.pack(side="right", padx=(10, 0))
        self.chk_auto_scroll.select()
        add_tooltip(self.chk_auto_scroll, "Automatically scroll to the newest log entries as they arrive.")

        self.btn_clear_logs = self._create_tonal_btn(top_bar, "Clear", self._clear_logs)
        self.btn_clear_logs.pack(side="right", padx=(6, 0))
        add_tooltip(self.btn_clear_logs, "Clear the contents of the activity log file.")

        self.btn_copy_logs = self._create_tonal_btn(top_bar, "Copy", self._copy_logs)
        self.btn_copy_logs.pack(side="right")
        add_tooltip(self.btn_copy_logs, "Copy all visible log text to your system clipboard.")

        # Dark Monospaced Terminal Frame
        term_frame = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["console_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        term_frame.pack(fill="both", expand=True)

        self.txt_logs = ctk.CTkTextbox(
            term_frame, font=get_macos_mono_font(size=12),
            wrap="word", corner_radius=APPLE_THEME["radius_card"],
            fg_color="transparent",
            text_color=APPLE_THEME["console_text"][0]
        )
        self.txt_logs.pack(fill="both", expand=True, padx=8, pady=8)

        return frame

    # -------------------------------------------------------------------------
    # TAB 4: DIAGNOSTICS (Network Doctor)
    # -------------------------------------------------------------------------
    def _build_diag_tab(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content_container, fg_color="transparent")

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header, text="Network & Gateway Diagnostic Suite",
            font=get_macos_font(size=16, weight="bold"),
            text_color=APPLE_THEME["text_primary"]
        ).pack(side="left")

        self.btn_run_diag = ctk.CTkButton(
            header, text="Run Full Diagnostics", width=160, height=34,
            font=get_macos_font(size=12, weight="bold"),
            fg_color=APPLE_THEME["accent_blue"],
            hover_color=APPLE_THEME["accent_blue_hover"],
            corner_radius=APPLE_THEME["radius_button"],
            command=self._start_diagnostics_thread
        )
        self.btn_run_diag.pack(side="right")
        add_tooltip(self.btn_run_diag, "Run automated tests for network adapter, DNS resolution, ping latency, and gateway reachability.")

        term_frame = ctk.CTkFrame(
            frame, corner_radius=APPLE_THEME["radius_card"],
            fg_color=APPLE_THEME["console_bg"],
            border_width=1, border_color=APPLE_THEME["card_border"]
        )
        term_frame.pack(fill="both", expand=True)

        self.txt_diag = ctk.CTkTextbox(
            term_frame, font=get_macos_mono_font(size=12),
            wrap="word", corner_radius=APPLE_THEME["radius_card"],
            fg_color="transparent",
            text_color=APPLE_THEME["console_text"][0]
        )
        self.txt_diag.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt_diag.insert(
            "1.0",
            "Network Doctor Ready.\nClick 'Run Full Diagnostics' to test DNS, ICMP echo, and FortiGate gateway challenge response.\n"
        )

        return frame

    # =========================================================================
    # NAVIGATION HANDLER & THEME TOGGLE
    # =========================================================================
    def _select_tab(self, tab_name: str):
        if hasattr(self, "tooltip_manager") and self.tooltip_manager:
            self.tooltip_manager.hide()

        self.current_tab = tab_name

        nav_map = [
            (self.btn_nav_status, "status"),
            (self.btn_nav_logs, "logs"),
            (self.btn_nav_diag, "diag"),
            (self.btn_nav_settings, "settings"),
        ]

        for btn, name in nav_map:
            if name == tab_name:
                btn.configure(
                    fg_color=APPLE_THEME["accent_blue"],
                    text_color="#FFFFFF",
                    font=get_macos_font(size=13, weight="bold")
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=APPLE_THEME["text_primary"],
                    font=get_macos_font(size=13, weight="normal")
                )

        self.tab_status.pack_forget()
        self.tab_settings.pack_forget()
        self.tab_logs.pack_forget()
        self.tab_diag.pack_forget()

        if tab_name == "status":
            self.tab_status.pack(fill="both", expand=True)
            self.refresh_all_status()
        elif tab_name == "settings":
            self.tab_settings.pack(fill="both", expand=True)
        elif tab_name == "logs":
            self.tab_logs.pack(fill="both", expand=True)
            self._update_logs_ui()
        elif tab_name == "diag":
            self.tab_diag.pack(fill="both", expand=True)

    def _change_appearance_mode(self, new_mode: str):
        ctk.set_appearance_mode(new_mode.lower())

    # =========================================================================
    # SYSTEM TRAY INTEGRATION (pystray)
    # =========================================================================
    def _setup_tray_icon(self):
        try:
            image = self._generate_badged_tray_icon("checking")
            menu = self._build_tray_menu()
            self.tray_icon = pystray.Icon("iiserb-login", image, "IISERB Login", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception:
            self.tray_icon = None

    def _generate_badged_tray_icon(self, status: str) -> Any:
        try:
            base = Image.open(self.icon_path).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            overlay = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            colors = {
                "online":   (52, 199, 89, 255),
                "offline":  (255, 59, 48, 255),
                "checking": (255, 149, 0, 255),
            }
            dot_color = colors.get(status, colors["offline"])

            cx, cy, r = 50, 50, 9
            draw.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=(24, 24, 27, 230))
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=dot_color)

            return Image.alpha_composite(base, overlay)
        except Exception:
            return Image.open(self.icon_path) if os.path.exists(self.icon_path) else None

    def _build_tray_menu(self):
        try:
            menu_items = [
                pystray.MenuItem("Open IISERB Portal", lambda: self._restore_and_navigate("status"), default=True),
                pystray.MenuItem("Force Login", lambda: self._handle_manual_login()),
                pystray.MenuItem("Reset Link", lambda: self._handle_reconnect_lan()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Preferences...", lambda: self._restore_and_navigate("settings")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit_app)
            ]
            return pystray.Menu(*menu_items)
        except Exception:
            return None

    def _on_window_close(self):
        if hasattr(self, "tooltip_manager") and self.tooltip_manager:
            self.tooltip_manager.hide()
        if self.tray_icon:
            self.withdraw()
            backend.send_notification("IISERB Login", "Minimized to system menu bar. Click tray icon to open.", urgency="low")
        else:
            self.destroy()

    def _restore_and_navigate(self, tab_name: str = "status"):
        self.after(0, lambda: (
            self.deiconify(),
            self.lift(),
            self.focus_force(),
            self._select_tab(tab_name)
        ))

    def _quit_app(self):
        if hasattr(self, "tooltip_manager") and self.tooltip_manager:
            self.tooltip_manager.hide()
        if self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self.destroy)

    def destroy(self):
        if hasattr(self, "tooltip_manager") and self.tooltip_manager:
            self.tooltip_manager.hide()
        try:
            super().destroy()
        except Exception:
            pass

    # =========================================================================
    # REAL-TIME MONITORING & BACKGROUND TASKS
    # =========================================================================
    def _start_periodic_monitoring(self):
        def monitor_loop():
            while True:
                try:
                    if self.current_tab == "status":
                        self._update_network_status_worker()
                        self._update_service_status_worker()
                    elif self.current_tab == "logs" and self.log_auto_refresh:
                        self._update_logs_worker()
                except Exception:
                    pass
                time.sleep(4)

        threading.Thread(target=monitor_loop, daemon=True).start()

    def refresh_all_status(self):
        threading.Thread(target=self._update_network_status_worker, daemon=True).start()
        threading.Thread(target=self._update_service_status_worker, daemon=True).start()

    def _update_network_status_worker(self):
        cfg = backend.load_config()
        is_online, latency = backend.check_internet(cfg.get("PING_TARGET", "1.1.1.1"))
        net_info = backend.get_network_info()

        def update():
            if is_online:
                self.hero_dot.configure(fg_color=APPLE_THEME["accent_green"])
                self.lbl_hero_title.configure(text="Internet Connected")
                self.lbl_hero_sub.configure(text=f"Traffic authenticated via FortiGate - Ping latency {latency:.1f} ms")
                self.badge_status.configure(
                    text="CONNECTED",
                    fg_color=APPLE_THEME["accent_green_subtle"],
                    text_color=APPLE_THEME["accent_green"]
                )
                self.tile_latency.configure(text=f"{latency:.1f} ms")
                self.dot_sidebar.configure(fg_color=APPLE_THEME["accent_green"])
                self.lbl_sidebar_status_text.configure(text=f"Online ({latency:.0f} ms)")
                if self.tray_icon and TRAY_AVAILABLE:
                    try:
                        self.tray_icon.icon = self._generate_badged_tray_icon("online")
                    except Exception:
                        pass
            else:
                self.hero_dot.configure(fg_color=APPLE_THEME["accent_red"])
                self.lbl_hero_title.configure(text="Captive Challenge Active")
                self.lbl_hero_sub.configure(text="Authentication required by FortiGate gateway firewall")
                self.badge_status.configure(
                    text="ACTION REQUIRED",
                    fg_color=APPLE_THEME["accent_red_subtle"],
                    text_color=APPLE_THEME["accent_red"]
                )
                self.tile_latency.configure(text="Timeout")
                self.dot_sidebar.configure(fg_color=APPLE_THEME["accent_red"])
                self.lbl_sidebar_status_text.configure(text="Offline (Captive)")
                if self.tray_icon and TRAY_AVAILABLE:
                    try:
                        self.tray_icon.icon = self._generate_badged_tray_icon("offline")
                    except Exception:
                        pass

            self.tile_ip.configure(text=net_info.get("ip", "Unknown"))
            self.tile_dev.configure(text=net_info.get("interface", "Unknown"))
            self.tile_gw.configure(text=net_info.get("gateway", "Unknown"))

        self.after(0, update)

    def _update_service_status_worker(self):
        status = backend.get_service_status()

        def update():
            if status["active"]:
                pid_txt = f" (PID {status['pid']})" if status["pid"] else ""
                self.lbl_svc_capsule.configure(
                    text=f"Active{pid_txt}",
                    fg_color=APPLE_THEME["accent_green_subtle"],
                    text_color=APPLE_THEME["accent_green"]
                )
                self.btn_svc_start.configure(state="disabled")
                self.btn_svc_stop.configure(state="normal")
            else:
                self.lbl_svc_capsule.configure(
                    text="Inactive (Stopped)",
                    fg_color=APPLE_THEME["button_tonal_bg"],
                    text_color=APPLE_THEME["text_secondary"]
                )
                self.btn_svc_start.configure(state="normal")
                self.btn_svc_stop.configure(state="disabled")

            if status["enabled"]:
                self.switch_autostart.select()
            else:
                self.switch_autostart.deselect()

        self.after(0, update)

    # =========================================================================
    # ACTIONS & USER CONTROLS
    # =========================================================================
    def _handle_service_action(self, action: str):
        self.lbl_action_msg.configure(text=f"Executing service {action}...", text_color=APPLE_THEME["text_secondary"])

        def task():
            ok, msg = backend.control_service(action)
            self.after(0, lambda: self.lbl_action_msg.configure(
                text=msg, text_color=APPLE_THEME["accent_green"] if ok else APPLE_THEME["accent_red"]
            ))
            self._update_service_status_worker()

        threading.Thread(target=task, daemon=True).start()

    def _toggle_autostart(self):
        action = "enable" if self.switch_autostart.get() == 1 else "disable"
        threading.Thread(target=lambda: backend.control_service(action), daemon=True).start()

    def _handle_manual_login(self):
        self.btn_manual_login.configure(state="disabled", text="Authenticating...")
        self.lbl_action_msg.configure(
            text="Submitting credentials to FortiGate captive gateway...",
            text_color=APPLE_THEME["text_secondary"]
        )

        def task():
            ok, msg = backend.perform_login()

            def finish():
                self.btn_manual_login.configure(state="normal", text="Force Login Now")
                self.lbl_action_msg.configure(
                    text=msg, text_color=APPLE_THEME["accent_green"] if ok else APPLE_THEME["accent_red"]
                )
                self._update_network_status_worker()

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _handle_reconnect_lan(self):
        self.btn_reconnect_lan.configure(state="disabled", text="Resetting...")
        self.lbl_action_msg.configure(
            text="Refreshing network link (non-destructive ARP sync)...",
            text_color=APPLE_THEME["text_secondary"]
        )

        def task():
            ok, msg = backend.bounce_interface()

            def finish():
                self.btn_reconnect_lan.configure(state="normal", text="Reset Link")
                self.lbl_action_msg.configure(
                    text=msg, text_color=APPLE_THEME["accent_green"] if ok else APPLE_THEME["accent_red"]
                )
                self._update_network_status_worker()

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _handle_hard_restart_lan(self):
        self.btn_hard_restart.configure(state="disabled", text="Resetting...")
        self.lbl_action_msg.configure(
            text="Scheduling auto-reconnect timer in 10s and cycling Ethernet connection...",
            text_color=APPLE_THEME["accent_orange"]
        )

        def task():
            res = backend.hard_restart_lan(delay_sec=10)

            def finish():
                self.btn_hard_restart.configure(state="normal", text="Hard LAN Reset")
                if res.get("success"):
                    self.lbl_action_msg.configure(
                        text="Interface cycled. Reconnect timer active (10s). Re-authenticating shortly...",
                        text_color=APPLE_THEME["accent_green"]
                    )

                    def post_reconnect():
                        time.sleep(12)
                        self._update_network_status_worker()
                        backend.perform_login(auto_bounce=False)
                        self._update_network_status_worker()

                    threading.Thread(target=post_reconnect, daemon=True).start()
                else:
                    self.lbl_action_msg.configure(
                        text=res.get("message", "Hard LAN reset failed."),
                        text_color=APPLE_THEME["accent_red"]
                    )

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _handle_logout(self):
        self.lbl_action_msg.configure(text="Sending logout request...", text_color=APPLE_THEME["text_secondary"])

        def task():
            ok, msg = backend.perform_logout()
            self.after(0, lambda: self.lbl_action_msg.configure(
                text=msg, text_color=APPLE_THEME["accent_green"] if ok else APPLE_THEME["accent_red"]
            ))
            self._update_network_status_worker()

        threading.Thread(target=task, daemon=True).start()

    def _open_portal_browser(self):
        webbrowser.open("http://neverssl.com")

    # =========================================================================
    # PREFERENCES PERSISTENCE
    # =========================================================================
    def _handle_password_enter(self, event=None):
        self.lbl_settings_alert.configure(text="Saving credentials and initiating login...", text_color=APPLE_THEME["accent_blue"][0])
        saved_ok = self._save_settings(show_message=False)
        if saved_ok:
            self._select_tab("status")
            self._handle_manual_login()

    def _toggle_password_visibility(self):
        if self.chk_show_pass.get() == 1:
            self.entry_password.configure(show="")
        else:
            self.entry_password.configure(show="*")

    def _update_slider_label(self, val):
        self.lbl_slider_val.configure(text=f"{int(val)}s")

    def _update_ka_label(self, val):
        self.lbl_ka_val.configure(text=f"{int(val)} min")

    def _load_saved_settings_into_ui(self):
        cfg = backend.load_config()
        self.entry_username.delete(0, "end")
        self.entry_username.insert(0, cfg.get("USERNAME", ""))

        self.entry_password.delete(0, "end")
        self.entry_password.insert(0, cfg.get("PASSWORD", ""))

        self.entry_ping_target.delete(0, "end")
        self.entry_ping_target.insert(0, cfg.get("PING_TARGET", "1.1.1.1"))

        chk_int = int(cfg.get("CHECK_INTERVAL", 60))
        self.slider_interval.set(chk_int)
        self.lbl_slider_val.configure(text=f"{chk_int}s")

        ka_int = int(cfg.get("KEEPALIVE_INTERVAL", 3))
        self.slider_ka.set(ka_int)
        self.lbl_ka_val.configure(text=f"{ka_int} min")

        self.entry_gateway.delete(0, "end")
        self.entry_gateway.insert(0, cfg.get("GATEWAY", "https://gateway.iiserb.ac.in:1003"))

        self.combo_probe.set(cfg.get("PROBE_URL", "http://connectivity-check.ubuntu.com/"))

        if cfg.get("NOTIFICATIONS_ENABLED", True):
            self.switch_notifications.select()
        else:
            self.switch_notifications.deselect()

        if cfg.get("AUTO_HARD_BOUNCE", False):
            self.switch_auto_hard.select()
        else:
            self.switch_auto_hard.deselect()

    def _load_defaults_into_ui(self):
        cfg = backend.DEFAULT_CONFIG
        self.entry_username.delete(0, "end")
        self.entry_username.insert(0, cfg["USERNAME"])
        self.entry_password.delete(0, "end")
        self.entry_password.insert(0, cfg["PASSWORD"])
        self.entry_ping_target.delete(0, "end")
        self.entry_ping_target.insert(0, cfg["PING_TARGET"])
        self.slider_interval.set(cfg["CHECK_INTERVAL"])
        self.lbl_slider_val.configure(text=f"{cfg['CHECK_INTERVAL']}s")
        self.slider_ka.set(cfg["KEEPALIVE_INTERVAL"])
        self.lbl_ka_val.configure(text=f"{cfg['KEEPALIVE_INTERVAL']} min")
        self.entry_gateway.delete(0, "end")
        self.entry_gateway.insert(0, cfg["GATEWAY"])
        self.combo_probe.set(cfg["PROBE_URL"])
        self.switch_notifications.select()
        self.switch_auto_hard.deselect()
        self.lbl_settings_alert.configure(
            text="Defaults restored. Click 'Save Settings' to apply.",
            text_color=APPLE_THEME["accent_orange"]
        )

    def _save_settings(self, show_message: bool = True) -> bool:
        new_cfg = {
            "USERNAME": self.entry_username.get().strip(),
            "PASSWORD": self.entry_password.get(),
            "PING_TARGET": self.entry_ping_target.get().strip(),
            "CHECK_INTERVAL": int(self.slider_interval.get()),
            "KEEPALIVE_INTERVAL": int(self.slider_ka.get()),
            "GATEWAY": self.entry_gateway.get().strip(),
            "PROBE_URL": self.combo_probe.get().strip(),
            "NOTIFICATIONS_ENABLED": (self.switch_notifications.get() == 1),
            "AUTO_HARD_BOUNCE": (self.switch_auto_hard.get() == 1)
        }

        ok, msg = backend.save_config(new_cfg)
        if ok:
            if hasattr(self, "card_onboarding") and new_cfg["USERNAME"] and new_cfg["PASSWORD"]:
                self.card_onboarding.pack_forget()

            svc = backend.get_service_status()
            if svc["active"]:
                backend.control_service("restart")
                msg += " (Background service restarted with new settings)"

            if show_message:
                self.lbl_settings_alert.configure(text=f"{msg}", text_color=APPLE_THEME["accent_green"])
            return True
        else:
            if show_message:
                self.lbl_settings_alert.configure(text=f"{msg}", text_color=APPLE_THEME["accent_red"])
            return False

    # =========================================================================
    # CONSOLE LOGS & DIAGNOSTICS HELPERS
    # =========================================================================
    def _toggle_auto_scroll(self):
        self.log_auto_refresh = (self.chk_auto_scroll.get() == 1)

    def _update_logs_worker(self):
        content = backend.read_logs(max_lines=200)
        if content != self.last_log_content:
            self.last_log_content = content
            self.after(0, self._render_logs, content)

    def _update_logs_ui(self):
        content = backend.read_logs(max_lines=200)
        self.last_log_content = content
        self._render_logs(content)

    def _render_logs(self, text: str):
        query = self.entry_filter_logs.get().strip().lower() if hasattr(self, "entry_filter_logs") else ""
        if query:
            lines = [line for line in text.splitlines() if query in line.lower()]
            display_text = "\n".join(lines)
        else:
            display_text = text

        self.txt_logs.delete("1.0", "end")
        self.txt_logs.insert("end", display_text)
        if self.log_auto_refresh:
            self.txt_logs.see("end")

    def _filter_logs(self):
        self._render_logs(self.last_log_content)

    def _clear_logs(self):
        backend.clear_logs()
        self._update_logs_ui()

    def _copy_logs(self):
        text = self.txt_logs.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(text)

    def _start_diagnostics_thread(self):
        self.btn_run_diag.configure(state="disabled", text="Running...")
        self.txt_diag.delete("1.0", "end")
        self.txt_diag.insert("end", "=== Starting Diagnostics ===\n")

        def task():
            cfg = backend.load_config()
            target = cfg.get("PING_TARGET", "1.1.1.1")
            gateway = cfg.get("GATEWAY", "https://gateway.iiserb.ac.in:1003")
            probe = cfg.get("PROBE_URL", "http://connectivity-check.ubuntu.com/")

            net = backend.get_network_info()
            self._append_diag(f"\n[1] Local Network Info:\n    Interface: {net['interface']}\n    IP: {net['ip']}\n    Default Gateway: {net['gateway']}\n")

            self._append_diag("\n[2] DNS Resolution Test:")
            for host in ["gateway.iiserb.ac.in", "connectivity-check.ubuntu.com", "detectportal.firefox.com"]:
                try:
                    import socket
                    ip = socket.gethostbyname(host)
                    self._append_diag(f"    [PASS] {host} -> {ip}")
                except Exception as e:
                    self._append_diag(f"    [FAIL] {host} -> Resolution failed: {e}")

            self._append_diag(f"\n[3] External Ping Test to {target}:")
            try:
                res = subprocess.run(["ping", "-c", "3", "-W", "2", target], stdout=subprocess.PIPE, text=True, timeout=8)
                self._append_diag("    " + "\n    ".join(res.stdout.strip().split("\n")))
            except Exception as e:
                self._append_diag(f"    [FAIL] Ping failed: {e}")

            self._append_diag(f"\n[4] Captive Portal Probe ({probe}):")
            try:
                res = subprocess.run(["curl", "-k", "-s", "-i", "--connect-timeout", "5", probe], stdout=subprocess.PIPE, text=True, timeout=8)
                headers = [line for line in res.stdout.split("\r\n") if line.strip()][:10]
                self._append_diag("    " + "\n    ".join(headers))
            except Exception as e:
                self._append_diag(f"    [FAIL] Probe failed: {e}")

            self._append_diag(f"\n[5] Gateway Reachability ({gateway}):")
            try:
                res = subprocess.run(["curl", "-k", "-s", "-i", "--connect-timeout", "5", f"{gateway}/"], stdout=subprocess.PIPE, text=True, timeout=8)
                first_lines = res.stdout.strip().split("\n")[:6]
                self._append_diag("    " + "\n    ".join(first_lines) if first_lines else "    (Gateway connected, closed cleanly)")
            except Exception as e:
                self._append_diag(f"    [FAIL] Gateway connection: {e}")

            self._append_diag("\n=== Diagnostics Complete ===\n")
            self.after(0, lambda: self.btn_run_diag.configure(state="normal", text="Run Full Diagnostics"))

        threading.Thread(target=task, daemon=True).start()

    def _append_diag(self, text: str):
        self.after(0, lambda: (self.txt_diag.insert("end", text + "\n"), self.txt_diag.see("end")))


_GUI_LOCK_FILE = None


def _acquire_gui_lock():
    global _GUI_LOCK_FILE
    lock_path = os.path.join(tempfile.gettempdir(), f"iiserb_login_gui_{os.getuid()}.lock")
    try:
        f = open(lock_path, "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _GUI_LOCK_FILE = f
        return True
    except (IOError, BlockingIOError):
        return False


def main():
    if len(sys.argv) > 1 and sys.argv[1] not in ["--gui", "-g"]:
        import cli
        sys.exit(cli.handle_cli(sys.argv[1:]))

    if not _acquire_gui_lock():
        try:
            backend.send_notification(
                "IISERB Login",
                "Application is already running in background. Check your system tray or top bar.",
                urgency="normal"
            )
        except Exception:
            pass
        print("An instance of IISERB Login GUI is already running. Exiting.", file=sys.stderr)
        sys.exit(0)

    app = IISERBLoginApp()
    try:
        app.mainloop()
    finally:
        if hasattr(app, "tooltip_manager") and app.tooltip_manager:
            app.tooltip_manager.hide()
        if _GUI_LOCK_FILE:
            try:
                _GUI_LOCK_FILE.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
