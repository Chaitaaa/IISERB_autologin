#!/usr/bin/env python3
"""
IISER Bhopal Captive Portal Manager - Desktop Application
Built with CustomTkinter for a modern, native Linux experience.
"""

import os
import sys
import threading
import time
import webbrowser
import subprocess
from typing import Optional

# Ensure backend can be imported
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import customtkinter as ctk
import backend

# Set default appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class IISERBLoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("IISER Bhopal - Captive Portal Manager")
        self.geometry("940x640")
        self.minsize(860, 580)

        # Set window icon if available
        icon_path = os.path.join(APP_DIR, "icon.png")
        if os.path.exists(icon_path):
            try:
                # CustomTkinter supports iconphoto via Tkinter root
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                photo = ImageTk.PhotoImage(img)
                self.iconphoto(False, photo)
            except Exception:
                pass

        # State tracking
        self.current_tab = "status"
        self.is_checking_network = False
        self.log_auto_refresh = True
        self.last_log_content = ""

        # Configure layout (2 columns: Sidebar & Main Content)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._create_sidebar()
        self._create_main_content()

        # Start periodic background updates
        self._start_periodic_monitoring()

    # -------------------------------------------------------------------------
    # Layout Creation
    # -------------------------------------------------------------------------
    def _create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        # App Logo / Title
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="🌐 IISERB Portal",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 5))

        self.subtitle_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Network Auto-login",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Nav Buttons
        self.btn_nav_status = ctk.CTkButton(
            self.sidebar_frame, text="📊 Status & Controls",
            command=lambda: self._select_tab("status"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=38
        )
        self.btn_nav_status.grid(row=2, column=0, padx=15, pady=4, sticky="ew")

        self.btn_nav_settings = ctk.CTkButton(
            self.sidebar_frame, text="⚙️ Settings & Options",
            command=lambda: self._select_tab("settings"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=38
        )
        self.btn_nav_settings.grid(row=3, column=0, padx=15, pady=4, sticky="ew")

        self.btn_nav_logs = ctk.CTkButton(
            self.sidebar_frame, text="📜 Live Activity Logs",
            command=lambda: self._select_tab("logs"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=38
        )
        self.btn_nav_logs.grid(row=4, column=0, padx=15, pady=4, sticky="ew")

        self.btn_nav_diag = ctk.CTkButton(
            self.sidebar_frame, text="🩺 Diagnostics",
            command=lambda: self._select_tab("diag"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=38
        )
        self.btn_nav_diag.grid(row=5, column=0, padx=15, pady=4, sticky="new")

        # Appearance mode selector at sidebar bottom
        self.theme_label = ctk.CTkLabel(self.sidebar_frame, text="Appearance Theme:", font=ctk.CTkFont(size=11))
        self.theme_label.grid(row=6, column=0, padx=20, pady=(10, 2), sticky="w")
        self.theme_menu = ctk.CTkOptionMenu(
            self.sidebar_frame, values=["Dark", "Light", "System"],
            command=self._change_appearance_mode, height=28
        )
        self.theme_menu.grid(row=7, column=0, padx=15, pady=(0, 20), sticky="ew")
        self.theme_menu.set("Dark")

    def _create_main_content(self):
        # Container frame
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        # Tab Frames
        self.tab_status = self._build_status_tab()
        self.tab_settings = self._build_settings_tab()
        self.tab_logs = self._build_logs_tab()
        self.tab_diag = self._build_diag_tab()

        # Display initial tab
        self._select_tab("status")

    # -------------------------------------------------------------------------
    # TAB 1: STATUS & CONTROLS
    # -------------------------------------------------------------------------
    def _build_status_tab(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")

        # 1. Network Status Card
        card_net = ctk.CTkFrame(frame, corner_radius=10)
        card_net.pack(fill="x", pady=(0, 15), padx=5)

        net_header = ctk.CTkFrame(card_net, fg_color="transparent")
        net_header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            net_header, text="Network Connectivity", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left")

        self.btn_refresh_status = ctk.CTkButton(
            net_header, text="🔄 Check Now", width=100, height=28,
            command=self.refresh_all_status
        )
        self.btn_refresh_status.pack(side="right")

        # Network Info Details
        info_grid = ctk.CTkFrame(card_net, fg_color="transparent")
        info_grid.pack(fill="x", padx=15, pady=(0, 15))
        info_grid.grid_columnconfigure((0, 1, 2), weight=1)

        # Status badge
        self.badge_status = ctk.CTkButton(
            info_grid, text="Checking...", fg_color="#F59E0B", hover=False,
            height=40, font=ctk.CTkFont(size=15, weight="bold")
        )
        self.badge_status.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        # Latency
        self.lbl_latency = ctk.CTkLabel(
            info_grid, text="Latency: --", font=ctk.CTkFont(size=13)
        )
        self.lbl_latency.grid(row=0, column=1, padx=10, pady=5)

        # IP & Interface
        self.lbl_ip_info = ctk.CTkLabel(
            info_grid, text="IP: Resolving...", font=ctk.CTkFont(size=13)
        )
        self.lbl_ip_info.grid(row=0, column=2, padx=10, pady=5)

        # 2. Background Daemon Card
        card_service = ctk.CTkFrame(frame, corner_radius=10)
        card_service.pack(fill="x", pady=(0, 15), padx=5)

        ctk.CTkLabel(
            card_service, text="Background Keepalive Service",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        svc_content = ctk.CTkFrame(card_service, fg_color="transparent")
        svc_content.pack(fill="x", padx=15, pady=(0, 15))
        svc_content.grid_columnconfigure(0, weight=1)
        svc_content.grid_columnconfigure(1, weight=2)

        # Status text & toggle
        status_box = ctk.CTkFrame(svc_content, fg_color="transparent")
        status_box.grid(row=0, column=0, sticky="w")

        self.lbl_service_status = ctk.CTkLabel(
            status_box, text="Service: Checking...", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.lbl_service_status.pack(anchor="w")

        self.switch_autostart = ctk.CTkSwitch(
            status_box, text="Start on System Boot",
            command=self._toggle_autostart, font=ctk.CTkFont(size=13)
        )
        self.switch_autostart.pack(anchor="w", pady=(8, 0))

        # Service Buttons
        btn_box = ctk.CTkFrame(svc_content, fg_color="transparent")
        btn_box.grid(row=0, column=1, sticky="e")

        self.btn_svc_start = ctk.CTkButton(
            btn_box, text="▶ Start", width=85, height=32,
            fg_color="#10B981", hover_color="#059669",
            command=lambda: self._handle_service_action("start")
        )
        self.btn_svc_start.pack(side="left", padx=5)

        self.btn_svc_stop = ctk.CTkButton(
            btn_box, text="⏹ Stop", width=85, height=32,
            fg_color="#EF4444", hover_color="#DC2626",
            command=lambda: self._handle_service_action("stop")
        )
        self.btn_svc_stop.pack(side="left", padx=5)

        self.btn_svc_restart = ctk.CTkButton(
            btn_box, text="🔄 Restart", width=95, height=32,
            command=lambda: self._handle_service_action("restart")
        )
        self.btn_svc_restart.pack(side="left", padx=5)

        # 3. Actions Card
        card_actions = ctk.CTkFrame(frame, corner_radius=10)
        card_actions.pack(fill="x", pady=(0, 15), padx=5)

        ctk.CTkLabel(
            card_actions, text="Manual Quick Actions",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        act_btn_box = ctk.CTkFrame(card_actions, fg_color="transparent")
        act_btn_box.pack(fill="x", padx=15, pady=(0, 10))

        self.btn_manual_login = ctk.CTkButton(
            act_btn_box, text="🚀 Force Login Now", height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#3B82F6", hover_color="#2563EB",
            command=self._handle_manual_login
        )
        self.btn_manual_login.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.btn_reconnect_lan = ctk.CTkButton(
            act_btn_box, text="🔄 Reset LAN Link", height=38,
            fg_color="gray30", hover_color="gray20",
            command=self._handle_reconnect_lan
        )
        self.btn_reconnect_lan.pack(side="left", padx=(0, 10))

        self.btn_open_portal = ctk.CTkButton(
            act_btn_box, text="🌐 Open Portal", height=38,
            command=self._open_portal_browser
        )
        self.btn_open_portal.pack(side="left", padx=(0, 10))

        self.btn_logout = ctk.CTkButton(
            act_btn_box, text="🚪 Logout", height=38,
            fg_color="gray40", hover_color="gray30",
            command=self._handle_logout
        )
        self.btn_logout.pack(side="left", padx=(0, 0))

        # Action notification / alert label
        self.lbl_action_msg = ctk.CTkLabel(
            card_actions, text="", font=ctk.CTkFont(size=12), text_color="gray70"
        )
        self.lbl_action_msg.pack(anchor="w", padx=15, pady=(0, 10))

        return frame

    # -------------------------------------------------------------------------
    # TAB 2: SETTINGS & OPTIONS
    # -------------------------------------------------------------------------
    def _build_settings_tab(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")

        # 1. User Credentials Group
        card_creds = ctk.CTkFrame(frame, corner_radius=10)
        card_creds.pack(fill="x", pady=(0, 15), padx=5)

        ctk.CTkLabel(
            card_creds, text="User Credentials", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        cred_grid = ctk.CTkFrame(card_creds, fg_color="transparent")
        cred_grid.pack(fill="x", padx=15, pady=(0, 15))
        cred_grid.grid_columnconfigure(1, weight=1)

        # Username
        ctk.CTkLabel(cred_grid, text="Username (LDAP):", font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 15)
        )
        self.entry_username = ctk.CTkEntry(cred_grid, height=34)
        self.entry_username.grid(row=0, column=1, sticky="ew", pady=6)

        # Password
        ctk.CTkLabel(cred_grid, text="Password:", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, sticky="w", pady=6, padx=(0, 15)
        )
        pass_box = ctk.CTkFrame(cred_grid, fg_color="transparent")
        pass_box.grid(row=1, column=1, sticky="ew", pady=6)
        pass_box.grid_columnconfigure(0, weight=1)

        self.entry_password = ctk.CTkEntry(pass_box, show="•", height=34)
        self.entry_password.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.chk_show_pass = ctk.CTkCheckBox(
            pass_box, text="Show", width=60, command=self._toggle_password_visibility
        )
        self.chk_show_pass.grid(row=0, column=1)

        # 2. Connection Options Group
        card_opts = ctk.CTkFrame(frame, corner_radius=10)
        card_opts.pack(fill="x", pady=(0, 15), padx=5)

        ctk.CTkLabel(
            card_opts, text="Network & Keepalive Options", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        opt_grid = ctk.CTkFrame(card_opts, fg_color="transparent")
        opt_grid.pack(fill="x", padx=15, pady=(0, 15))
        opt_grid.grid_columnconfigure(1, weight=1)

        # Ping Target
        ctk.CTkLabel(opt_grid, text="Ping Target (DNS):", font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 15)
        )
        self.entry_ping_target = ctk.CTkEntry(opt_grid, height=34)
        self.entry_ping_target.grid(row=0, column=1, sticky="ew", pady=6)

        # Check Interval (Seconds)
        ctk.CTkLabel(opt_grid, text="Check Interval (sec):", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, sticky="w", pady=6, padx=(0, 15)
        )
        interval_box = ctk.CTkFrame(opt_grid, fg_color="transparent")
        interval_box.grid(row=1, column=1, sticky="ew", pady=6)
        interval_box.grid_columnconfigure(0, weight=1)

        self.slider_interval = ctk.CTkSlider(
            interval_box, from_=10, to=300, number_of_steps=29, command=self._update_slider_label
        )
        self.slider_interval.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.lbl_slider_val = ctk.CTkLabel(interval_box, text="60s", width=50)
        self.lbl_slider_val.grid(row=0, column=1)

        # Keepalive Interval (Minutes)
        ctk.CTkLabel(opt_grid, text="Keepalive Ping (min):", font=ctk.CTkFont(size=13)).grid(
            row=2, column=0, sticky="w", pady=6, padx=(0, 15)
        )
        ka_box = ctk.CTkFrame(opt_grid, fg_color="transparent")
        ka_box.grid(row=2, column=1, sticky="ew", pady=6)
        ka_box.grid_columnconfigure(0, weight=1)

        self.slider_ka = ctk.CTkSlider(
            ka_box, from_=1, to=30, number_of_steps=29, command=self._update_ka_label
        )
        self.slider_ka.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.lbl_ka_val = ctk.CTkLabel(ka_box, text="10 min", width=50)
        self.lbl_ka_val.grid(row=0, column=1)

        # Gateway URL
        ctk.CTkLabel(opt_grid, text="Gateway URL:", font=ctk.CTkFont(size=13)).grid(
            row=3, column=0, sticky="w", pady=6, padx=(0, 15)
        )
        self.entry_gateway = ctk.CTkEntry(opt_grid, height=34)
        self.entry_gateway.grid(row=3, column=1, sticky="ew", pady=6)

        # Probe URL
        ctk.CTkLabel(opt_grid, text="Probe URL:", font=ctk.CTkFont(size=13)).grid(
            row=4, column=0, sticky="w", pady=6, padx=(0, 15)
        )
        self.combo_probe = ctk.CTkComboBox(
            opt_grid, height=34,
            values=[
                "http://connectivity-check.ubuntu.com/",
                "http://detectportal.firefox.com/success.txt",
                "http://neverssl.com",
                "http://clients3.google.com/generate_204"
            ]
        )
        self.combo_probe.grid(row=4, column=1, sticky="ew", pady=6)

        # Save & Reset Buttons
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=5, pady=(5, 10))

        self.btn_save_settings = ctk.CTkButton(
            btn_row, text="💾 Save Settings & Apply", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10B981", hover_color="#059669",
            command=self._save_settings
        )
        self.btn_save_settings.pack(side="left", padx=(0, 10))

        self.btn_reset_defaults = ctk.CTkButton(
            btn_row, text="↺ Reset Defaults", height=40,
            fg_color="gray40", hover_color="gray30",
            command=self._load_defaults_into_ui
        )
        self.btn_reset_defaults.pack(side="left")

        self.lbl_settings_alert = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=13)
        )
        self.lbl_settings_alert.pack(anchor="w", padx=10, pady=(0, 10))

        # Populate settings
        self._load_saved_settings_into_ui()

        return frame

    # -------------------------------------------------------------------------
    # TAB 3: LIVE ACTIVITY LOGS
    # -------------------------------------------------------------------------
    def _build_logs_tab(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content_container, fg_color="transparent")

        top_bar = ctk.CTkFrame(frame, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            top_bar, text="Live Log Stream (/tmp/iiserb_autologin.log)",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left")

        self.chk_auto_scroll = ctk.CTkCheckBox(top_bar, text="Auto-refresh", command=self._toggle_auto_scroll)
        self.chk_auto_scroll.pack(side="right", padx=(10, 0))
        self.chk_auto_scroll.select()

        self.btn_clear_logs = ctk.CTkButton(
            top_bar, text="🗑 Clear", width=80, height=28, command=self._clear_logs
        )
        self.btn_clear_logs.pack(side="right", padx=(10, 0))

        self.btn_copy_logs = ctk.CTkButton(
            top_bar, text="📋 Copy", width=80, height=28, command=self._copy_logs
        )
        self.btn_copy_logs.pack(side="right")

        # Log text area
        self.txt_logs = ctk.CTkTextbox(
            frame, font=ctk.CTkFont(family="monospace", size=12),
            wrap="word", corner_radius=8
        )
        self.txt_logs.pack(fill="both", expand=True)

        return frame

    # -------------------------------------------------------------------------
    # TAB 4: DIAGNOSTICS
    # -------------------------------------------------------------------------
    def _build_diag_tab(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content_container, fg_color="transparent")

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header, text="Network & Gateway Diagnostic Suite",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left")

        self.btn_run_diag = ctk.CTkButton(
            header, text="▶ Run Diagnostics", width=140, height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_diagnostics_thread
        )
        self.btn_run_diag.pack(side="right")

        self.txt_diag = ctk.CTkTextbox(
            frame, font=ctk.CTkFont(family="monospace", size=12),
            wrap="word", corner_radius=8
        )
        self.txt_diag.pack(fill="both", expand=True)
        self.txt_diag.insert("1.0", "Click 'Run Diagnostics' above to inspect DNS, gateway reachability, and portal response.\n")

        return frame

    # -------------------------------------------------------------------------
    # Navigation Handler
    # -------------------------------------------------------------------------
    def _select_tab(self, tab_name: str):
        self.current_tab = tab_name

        # Reset button styles
        for btn, name in [
            (self.btn_nav_status, "status"),
            (self.btn_nav_settings, "settings"),
            (self.btn_nav_logs, "logs"),
            (self.btn_nav_diag, "diag"),
        ]:
            if name == tab_name:
                btn.configure(fg_color=("gray75", "gray25"), font=ctk.CTkFont(weight="bold"))
            else:
                btn.configure(fg_color="transparent", font=ctk.CTkFont(weight="normal"))

        # Hide all tabs
        self.tab_status.pack_forget()
        self.tab_settings.pack_forget()
        self.tab_logs.pack_forget()
        self.tab_diag.pack_forget()

        # Show selected tab
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

    # -------------------------------------------------------------------------
    # Real-Time Monitoring & Status Checks
    # -------------------------------------------------------------------------
    def _start_periodic_monitoring(self):
        def monitor_loop():
            while True:
                try:
                    if self.current_tab == "status":
                        self._update_network_status_worker()
                        self._update_service_status_worker()
                    elif self.current_tab == "logs" and self.log_auto_refresh:
                        self._update_logs_worker()
                except Exception as e:
                    pass
                time.sleep(4)

        t = threading.Thread(target=monitor_loop, daemon=True)
        t.start()

    def refresh_all_status(self):
        threading.Thread(target=self._update_network_status_worker, daemon=True).start()
        threading.Thread(target=self._update_service_status_worker, daemon=True).start()

    def _update_network_status_worker(self):
        cfg = backend.load_config()
        is_online, latency = backend.check_internet(cfg.get("PING_TARGET", "1.1.1.1"))
        net_info = backend.get_network_info()

        def update():
            if is_online:
                self.badge_status.configure(
                    text="🟢 ONLINE (Connected)",
                    fg_color="#10B981"
                )
                self.lbl_latency.configure(text=f"Latency: {latency:.1f} ms")
            else:
                self.badge_status.configure(
                    text="🔴 OFFLINE (Captive Portal)",
                    fg_color="#EF4444"
                )
                self.lbl_latency.configure(text="Latency: Timeout")

            self.lbl_ip_info.configure(
                text=f"IP: {net_info['ip']} ({net_info['interface']}) | GW: {net_info['gateway']}"
            )

        self.after(0, update)

    def _update_service_status_worker(self):
        status = backend.get_service_status()

        def update():
            if status["active"]:
                pid_txt = f" (PID {status['pid']})" if status["pid"] else ""
                self.lbl_service_status.configure(
                    text=f"Service: 🟢 Active{pid_txt}",
                    text_color="#10B981"
                )
                self.btn_svc_start.configure(state="disabled")
                self.btn_svc_stop.configure(state="normal")
            else:
                self.lbl_service_status.configure(
                    text="Service: ⚪ Inactive (Stopped)",
                    text_color="gray70"
                )
                self.btn_svc_start.configure(state="normal")
                self.btn_svc_stop.configure(state="disabled")

            # Update toggle switch without triggering command
            if status["enabled"]:
                self.switch_autostart.select()
            else:
                self.switch_autostart.deselect()

        self.after(0, update)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def _handle_service_action(self, action: str):
        self.lbl_action_msg.configure(text=f"Executing service {action}...", text_color="gray70")

        def task():
            ok, msg = backend.control_service(action)
            self.after(0, lambda: self.lbl_action_msg.configure(
                text=msg, text_color="#10B981" if ok else "#EF4444"
            ))
            self._update_service_status_worker()

        threading.Thread(target=task, daemon=True).start()

    def _toggle_autostart(self):
        action = "enable" if self.switch_autostart.get() == 1 else "disable"
        threading.Thread(target=lambda: backend.control_service(action), daemon=True).start()

    def _handle_manual_login(self):
        self.btn_manual_login.configure(state="disabled", text="⏳ Logging in...")
        self.lbl_action_msg.configure(text="Sending authentication request to FortiGate gateway...", text_color="gray70")

        def task():
            ok, msg = backend.perform_login()

            def finish():
                self.btn_manual_login.configure(state="normal", text="🚀 Force Login Now")
                self.lbl_action_msg.configure(
                    text=msg, text_color="#10B981" if ok else "#EF4444"
                )
                self._update_network_status_worker()

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _handle_reconnect_lan(self):
        self.btn_reconnect_lan.configure(state="disabled", text="⏳ Resetting...")
        self.lbl_action_msg.configure(text="Refreshing network link via NetworkManager...", text_color="gray70")

        def task():
            ok, msg = backend.bounce_interface()

            def finish():
                self.btn_reconnect_lan.configure(state="normal", text="🔄 Reset LAN Link")
                self.lbl_action_msg.configure(
                    text=msg, text_color="#10B981" if ok else "#EF4444"
                )
                self._update_network_status_worker()

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _handle_logout(self):
        self.lbl_action_msg.configure(text="Sending logout request...", text_color="gray70")

        def task():
            ok, msg = backend.perform_logout()
            self.after(0, lambda: self.lbl_action_msg.configure(
                text=msg, text_color="#10B981" if ok else "#EF4444"
            ))
            self._update_network_status_worker()

        threading.Thread(target=task, daemon=True).start()

    def _open_portal_browser(self):
        webbrowser.open("http://neverssl.com")

    # -------------------------------------------------------------------------
    # Settings Management
    # -------------------------------------------------------------------------
    def _toggle_password_visibility(self):
        if self.chk_show_pass.get() == 1:
            self.entry_password.configure(show="")
        else:
            self.entry_password.configure(show="•")

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

        ka_int = int(cfg.get("KEEPALIVE_INTERVAL", 10))
        self.slider_ka.set(ka_int)
        self.lbl_ka_val.configure(text=f"{ka_int} min")

        self.entry_gateway.delete(0, "end")
        self.entry_gateway.insert(0, cfg.get("GATEWAY", "https://gateway.iiserb.ac.in:1003"))

        self.combo_probe.set(cfg.get("PROBE_URL", "http://connectivity-check.ubuntu.com/"))

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
        self.lbl_settings_alert.configure(
            text="Defaults restored in fields. Click 'Save Settings' to apply.",
            text_color="#F59E0B"
        )

    def _save_settings(self):
        new_cfg = {
            "USERNAME": self.entry_username.get().strip(),
            "PASSWORD": self.entry_password.get(),
            "PING_TARGET": self.entry_ping_target.get().strip(),
            "CHECK_INTERVAL": int(self.slider_interval.get()),
            "KEEPALIVE_INTERVAL": int(self.slider_ka.get()),
            "GATEWAY": self.entry_gateway.get().strip(),
            "PROBE_URL": self.combo_probe.get().strip()
        }

        ok, msg = backend.save_config(new_cfg)
        if ok:
            # If service is active, restart it so new settings take effect immediately
            svc = backend.get_service_status()
            if svc["active"]:
                backend.control_service("restart")
                msg += " (Background service restarted with new settings)"

            self.lbl_settings_alert.configure(text=f"✅ {msg}", text_color="#10B981")
        else:
            self.lbl_settings_alert.configure(text=f"❌ {msg}", text_color="#EF4444")

    # -------------------------------------------------------------------------
    # Logs View
    # -------------------------------------------------------------------------
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
        self.txt_logs.delete("1.0", "end")
        self.txt_logs.insert("end", text)
        self.txt_logs.see("end")

    def _clear_logs(self):
        backend.clear_logs()
        self._update_logs_ui()

    def _copy_logs(self):
        text = self.txt_logs.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(text)

    # -------------------------------------------------------------------------
    # Diagnostics Suite
    # -------------------------------------------------------------------------
    def _start_diagnostics_thread(self):
        self.btn_run_diag.configure(state="disabled", text="Running...")
        self.txt_diag.delete("1.0", "end")
        self.txt_diag.insert("end", "=== Starting Diagnostics ===\n")

        def task():
            cfg = backend.load_config()
            target = cfg.get("PING_TARGET", "1.1.1.1")
            gateway = cfg.get("GATEWAY", "https://gateway.iiserb.ac.in:1003")
            probe = cfg.get("PROBE_URL", "http://connectivity-check.ubuntu.com/")

            # Test 1: Interface & Local IP
            net = backend.get_network_info()
            self._append_diag(f"\n[1] Local Network Info:\n    Interface: {net['interface']}\n    IP: {net['ip']}\n    Default Gateway: {net['gateway']}\n")

            # Test 2: DNS Resolution
            self._append_diag(f"\n[2] DNS Resolution Test:")
            for host in ["gateway.iiserb.ac.in", "connectivity-check.ubuntu.com", "detectportal.firefox.com"]:
                try:
                    import socket
                    ip = socket.gethostbyname(host)
                    self._append_diag(f"    ✔ {host} -> {ip}")
                except Exception as e:
                    self._append_diag(f"    ❌ {host} -> Resolution failed: {e}")

            # Test 3: Ping Check
            self._append_diag(f"\n[3] External Ping Test to {target}:")
            try:
                res = subprocess.run(["ping", "-c", "3", "-W", "2", target], stdout=subprocess.PIPE, text=True, timeout=8)
                self._append_diag("    " + "\n    ".join(res.stdout.strip().split("\n")))
            except Exception as e:
                self._append_diag(f"    ❌ Ping failed: {e}")

            # Test 4: Captive Portal Probe Test
            self._append_diag(f"\n[4] Captive Portal Probe ({probe}):")
            try:
                res = subprocess.run(["curl", "-k", "-s", "-i", "--connect-timeout", "5", probe], stdout=subprocess.PIPE, text=True, timeout=8)
                headers = [line for line in res.stdout.split("\r\n") if line.strip()][:10]
                self._append_diag("    " + "\n    ".join(headers))
            except Exception as e:
                self._append_diag(f"    ❌ Probe failed: {e}")

            # Test 5: Gateway Reachability
            self._append_diag(f"\n[5] Gateway Reachability ({gateway}):")
            try:
                res = subprocess.run(["curl", "-k", "-s", "-i", "--connect-timeout", "5", f"{gateway}/"], stdout=subprocess.PIPE, text=True, timeout=8)
                first_lines = res.stdout.strip().split("\n")[:6]
                self._append_diag("    " + "\n    ".join(first_lines) if first_lines else "    (Gateway connected, closed cleanly)")
            except Exception as e:
                self._append_diag(f"    ❌ Gateway connection: {e}")

            self._append_diag("\n=== Diagnostics Complete ===\n")

            self.after(0, lambda: self.btn_run_diag.configure(state="normal", text="▶ Run Diagnostics"))

        threading.Thread(target=task, daemon=True).start()

    def _append_diag(self, text: str):
        self.after(0, lambda: (self.txt_diag.insert("end", text + "\n"), self.txt_diag.see("end")))


def main():
    app = IISERBLoginApp()
    app.mainloop()


if __name__ == "__main__":
    main()
