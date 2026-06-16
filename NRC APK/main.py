# -*- coding: utf-8 -*-
import flet as ft
import requests
import threading
import time

API_BASE_URL = "https://leos-nrc-automation.onrender.com"
LIVE_SITE_URL = "https://nnnrc.com/#/mytask"

# ── Design Tokens ─────────────────────────────────────────────────────────────
WHITE          = "#FFFFFF"
BG_PAGE        = "#F7F9FA"
ACCENT         = "#16A34A"
ACCENT_LIGHT   = "#22C55E"
TEXT_PRIMARY   = "#1F2937"
TEXT_SECONDARY = "#6B7280"
TEXT_HINT      = "#9CA3AF"
BORDER         = "#E5E7EB"
CARD_SHADOW    = "#0000000D"

STATUS_IDLE_BG  = "#F0FDF4"; STATUS_IDLE_FG  = "#15803D"; STATUS_IDLE_DOT  = ACCENT
STATUS_RUN_BG   = "#DCFCE7"; STATUS_RUN_FG   = "#166534"; STATUS_RUN_DOT   = ACCENT
STATUS_STR_BG   = "#FEF9C3"; STATUS_STR_FG   = "#854D0E"; STATUS_STR_DOT   = "#EAB308"
STATUS_DONE_BG  = "#F0FDF4"; STATUS_DONE_FG  = "#15803D"; STATUS_DONE_DOT  = ACCENT
STATUS_ERR_BG   = "#FEE2E2"; STATUS_ERR_FG   = "#DC2626"; STATUS_ERR_DOT   = "#DC2626"

LOG_DEFAULT = "#374151"
LOG_SUCCESS = "#15803D"
LOG_ERROR   = "#DC2626"
LOG_WARN    = "#92400E"
LOG_INFO    = "#1D4ED8"


def card(content, height=None):
    """Glass card: white bg, 1px border, subtle shadow, 16px radius."""
    kwargs = dict(
        content=content,
        bgcolor=WHITE,
        border_radius=16,
        padding=ft.padding.only(left=18, top=16, right=18, bottom=18),
        border=ft.border.all(1, BORDER),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=14,
            color=CARD_SHADOW,
            offset=ft.Offset(0, 3),
        ),
    )
    if height:
        kwargs["height"] = height
    return ft.Container(**kwargs)


def section_label(text):
    """Small all-caps section label with green left-bar accent."""
    return ft.Row(
        [
            ft.Container(width=3, height=13, bgcolor=ACCENT, border_radius=2),
            ft.Text(
                text,
                size=10,
                weight=ft.FontWeight.W_700,
                color=TEXT_SECONDARY,
                style=ft.TextStyle(letter_spacing=1.1),
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def icon_pill(icon, bg="#F0FDF4", border_color="#D1FAE5", icon_color=ACCENT,
              icon_size=16, padding_val=7):
    """Small icon in a rounded green pill."""
    return ft.Container(
        content=ft.Icon(icon, color=icon_color, size=icon_size),
        bgcolor=bg,
        border_radius=8,
        padding=padding_val,
        border=ft.border.all(1, border_color),
    )


def main(page: ft.Page):
    # ── Page Setup ────────────────────────────────────────────────────────────
    page.title         = "Leo's NRC Automator"
    page.theme_mode    = ft.ThemeMode.LIGHT
    page.window_width  = 420
    page.window_height = 820
    page.window_resizable = False
    page.padding       = 0
    page.scroll        = None
    page.bgcolor       = BG_PAGE
    page.fonts         = {
        "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    }
    page.theme = ft.Theme(
        font_family="Inter",
        color_scheme=ft.ColorScheme(primary=ACCENT),
    )

    state = {"job_id": None, "is_running": False}

    # ═══════════════════════════════════════════════════════════════════════════
    # STATUS WIDGETS
    # ═══════════════════════════════════════════════════════════════════════════
    _dot   = ft.Container(width=7, height=7, bgcolor=STATUS_IDLE_DOT, border_radius=4)
    _label = ft.Text("IDLE", size=11, weight=ft.FontWeight.W_600, color=STATUS_IDLE_FG)
    status_badge = ft.Container(
        content=ft.Row([_dot, _label], spacing=5, tight=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=STATUS_IDLE_BG,
        border_radius=20,
        padding=ft.padding.symmetric(horizontal=11, vertical=5),
    )

    completed_text = ft.Text("0 / 0 tasks", size=13, color=TEXT_SECONDARY,
                             weight=ft.FontWeight.W_500)
    progress_ring  = ft.ProgressRing(visible=False, color=ACCENT,
                                     width=15, height=15, stroke_width=2)

    def set_status(label, bg, fg, dot):
        _label.value  = label
        _label.color  = fg
        _dot.bgcolor  = dot
        status_badge.bgcolor = bg
        page.update()

    # ═══════════════════════════════════════════════════════════════════════════
    # LOG PANEL
    # ═══════════════════════════════════════════════════════════════════════════
    log_list = ft.ListView(expand=True, spacing=2, auto_scroll=True, padding=0)

    empty_icon = ft.Icon(ft.icons.RECEIPT_LONG_OUTLINED, color="#D1D5DB", size=36)
    empty_line1 = ft.Text("No execution logs yet.", size=13, color=TEXT_SECONDARY,
                          weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER)
    empty_line2 = ft.Text("Your activity will appear here.", size=12, color=TEXT_HINT,
                          text_align=ft.TextAlign.CENTER)

    empty_state = ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        visible=True,
        content=ft.Column(
            [ft.Container(content=empty_icon, margin=ft.margin.only(bottom=8)),
             empty_line1, empty_line2],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=4,
        ),
    )

    log_body = ft.Stack([empty_state, log_list], expand=True)

    def append_log(msg, color=LOG_DEFAULT, do_update=True):
        if empty_state.visible:
            empty_state.visible = False
        log_list.controls.append(
            ft.Container(
                content=ft.Text(msg, size=12, color=color, selectable=True),
                padding=ft.padding.symmetric(vertical=1),
            )
        )
        if do_update:
            page.update()

    # ═══════════════════════════════════════════════════════════════════════════
    # INPUT FIELDS
    # ═══════════════════════════════════════════════════════════════════════════
    _field = dict(
        border_radius=14,
        border_color=BORDER,
        focused_border_color=ACCENT,
        border_width=1.5,
        focused_border_width=2,
        bgcolor=WHITE,
        focused_bgcolor=WHITE,
        color=TEXT_PRIMARY,
        cursor_color=ACCENT,
        label_style=ft.TextStyle(color=TEXT_HINT, size=13),
        text_style=ft.TextStyle(size=14, color=TEXT_PRIMARY),
    )

    phone_input    = ft.TextField(label="Phone Number",
                                  prefix_icon=ft.icons.PHONE_OUTLINED,
                                  keyboard_type=ft.KeyboardType.PHONE, **_field)
    password_input = ft.TextField(label="Password",
                                  prefix_icon=ft.icons.LOCK_OUTLINE,
                                  password=True, can_reveal_password=True, **_field)

    # ═══════════════════════════════════════════════════════════════════════════
    # START BUTTON
    # ═══════════════════════════════════════════════════════════════════════════
    start_btn = ft.ElevatedButton(
        content=ft.Row(
            [ft.Icon(ft.icons.PLAY_ARROW_ROUNDED, color=WHITE, size=18),
             ft.Text("Start Automating", size=14, weight=ft.FontWeight.W_600,
                     color=WHITE)],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        ),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=14),
            bgcolor={"": ACCENT, "hovered": "#15803D", "pressed": "#166534",
                     "disabled": "#D1D5DB"},
            overlay_color="#FFFFFF18",
            elevation={"": 2, "hovered": 5, "disabled": 0},
            shadow_color="#16A34A30",
            padding=ft.padding.symmetric(vertical=15),
        ),
        on_click=lambda e: _start(e),
        width=float("inf"),
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # POLLING
    # ═══════════════════════════════════════════════════════════════════════════
    def _poll():
        seen = 0
        poll_failures = 0
        while state["is_running"] and state["job_id"]:
            try:
                r = requests.get(f"{API_BASE_URL}/status/{state['job_id']}", timeout=10)
                poll_failures = 0
                if r.status_code == 200:
                    d = r.json()
                    js = d.get("status", "running")
                    completed_text.value = f"{d.get('completed', 0)} / {d.get('total', 0)} tasks"
                    for entry in d.get("log", [])[seen:]:
                        if any(x in entry for x in ("✅", "done", "success", "SUCCESS")):
                            col = LOG_SUCCESS
                        elif any(x in entry for x in ("❌", "error", "fail", "Error")):
                            col = LOG_ERROR
                        elif any(x in entry for x in ("⏳", "⏸", "🔄", "📡", "📋", "🔑")):
                            col = LOG_WARN
                        elif any(x in entry for x in ("🤖", "🏁")):
                            col = LOG_INFO
                        else:
                            col = LOG_DEFAULT
                        append_log(entry, col, do_update=False)
                        seen += 1
                    if js in ("finished", "error"):
                        state["is_running"]   = False
                        start_btn.disabled    = False
                        progress_ring.visible = False
                        if js == "finished":
                            set_status("DONE ✓", STATUS_DONE_BG, STATUS_DONE_FG, STATUS_DONE_DOT)
                        else:
                            set_status("ERROR", STATUS_ERR_BG, STATUS_ERR_FG, STATUS_ERR_DOT)
                    page.update()
                    if not state["is_running"]:
                        break
            except Exception:
                poll_failures += 1
                # Transient DNS/timeouts on Render free tier — retry silently
                if poll_failures % 10 == 0:
                    append_log("⚠️  Brief connection hiccup — still running…", LOG_WARN)
            time.sleep(3)

    def _start(e):
        phone = phone_input.value.strip()
        pwd   = password_input.value.strip()
        if not phone or not pwd:
            append_log("⚠️  Enter phone and password first.", LOG_WARN)
            return
        start_btn.disabled    = True
        progress_ring.visible = True
        log_list.controls.clear()
        empty_state.visible   = False
        completed_text.value  = "0 / 0 tasks"
        set_status("STARTING", STATUS_STR_BG, STATUS_STR_FG, STATUS_STR_DOT)
        page.update()
        try:
            append_log("📡  Connecting to automation server...")
            r = requests.post(f"{API_BASE_URL}/start",
                              json={"phone": phone, "password": pwd}, timeout=20)
            d = r.json()
            if r.status_code == 200 and "job_id" in d:
                state["job_id"]     = d["job_id"]
                state["is_running"] = True
                append_log(f"✅  Session started · ID: {d['job_id'][:8]}…", LOG_SUCCESS)
                set_status("RUNNING", STATUS_RUN_BG, STATUS_RUN_FG, STATUS_RUN_DOT)
                threading.Thread(target=_poll, daemon=True).start()
            else:
                append_log(f"❌  Failed: {d.get('error', d)}", LOG_ERROR)
                start_btn.disabled    = False
                progress_ring.visible = False
                set_status("IDLE", STATUS_IDLE_BG, STATUS_IDLE_FG, STATUS_IDLE_DOT)
        except Exception as ex:
            append_log(f"❌  Network error: {ex}", LOG_ERROR)
            start_btn.disabled    = False
            progress_ring.visible = False
            set_status("IDLE", STATUS_IDLE_BG, STATUS_IDLE_FG, STATUS_IDLE_DOT)
        page.update()

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 1 — BOT
    # ═══════════════════════════════════════════════════════════════════════════
    bot_tab = ft.Container(
        bgcolor=BG_PAGE,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[

                # ── Header bar ────────────────────────────────────────────────
                ft.Container(
                    bgcolor=WHITE,
                    padding=ft.padding.only(left=22, top=22, right=22, bottom=18),
                    border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                    content=ft.Row(
                        [
                            icon_pill(ft.icons.BOLT_OUTLINED, icon_size=22,
                                      padding_val=9),
                            ft.Column(
                                [
                                    ft.Text("Leo's NRC Automator", size=18,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT_PRIMARY),
                                    ft.Text("by Leo Emmanuel", size=11,
                                            color=TEXT_SECONDARY,
                                            weight=ft.FontWeight.W_400),
                                ],
                                spacing=1,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=13,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),

                # ── Scrollable body ───────────────────────────────────────────
                ft.Container(
                    expand=True,
                    content=ft.Column(
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                        spacing=0,
                        controls=[

                            # Credentials card
                            ft.Container(
                                margin=ft.margin.only(left=16, top=18, right=16),
                                content=card(
                                    ft.Column(
                                        [
                                            section_label("ACCOUNT CREDENTIALS"),
                                            ft.Container(height=14),
                                            phone_input,
                                            ft.Container(height=10),
                                            password_input,
                                        ],
                                        spacing=0,
                                    )
                                ),
                            ),

                            # Start button
                            ft.Container(
                                margin=ft.margin.only(left=16, top=14, right=16),
                                content=start_btn,
                            ),

                            # Status row card
                            ft.Container(
                                margin=ft.margin.only(left=16, top=12, right=16),
                                content=ft.Container(
                                    bgcolor=WHITE,
                                    border_radius=12,
                                    padding=ft.padding.symmetric(horizontal=16,
                                                                  vertical=12),
                                    border=ft.border.all(1, BORDER),
                                    content=ft.Row(
                                        [
                                            progress_ring,
                                            status_badge,
                                            ft.Container(expand=True),
                                            ft.Icon(ft.icons.TASK_ALT_OUTLINED,
                                                    color=TEXT_HINT, size=14),
                                            completed_text,
                                        ],
                                        spacing=10,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                ),
                            ),

                            # Execution log card
                            ft.Container(
                                margin=ft.margin.only(left=16, top=14,
                                                      right=16, bottom=20),
                                content=card(
                                    ft.Column(
                                        [
                                            # Log header row
                                            ft.Row(
                                                [
                                                    icon_pill(
                                                        ft.icons.TERMINAL_OUTLINED,
                                                        icon_size=14,
                                                        padding_val=5,
                                                    ),
                                                    ft.Text("Execution Log", size=12,
                                                            weight=ft.FontWeight.W_600,
                                                            color=TEXT_PRIMARY),
                                                    ft.Container(expand=True),
                                                    ft.Container(
                                                        content=ft.Text(
                                                            "LIVE", size=9,
                                                            weight=ft.FontWeight.W_700,
                                                            color=ACCENT,
                                                            style=ft.TextStyle(letter_spacing=0.8),
                                                        ),
                                                        bgcolor="#F0FDF4",
                                                        border_radius=8,
                                                        padding=ft.padding.symmetric(
                                                            horizontal=8, vertical=3),
                                                        border=ft.border.all(1, "#BBF7D0"),
                                                    ),
                                                ],
                                                spacing=8,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                            # Divider
                                            ft.Container(
                                                height=1, bgcolor=BORDER,
                                                margin=ft.margin.symmetric(vertical=10),
                                            ),
                                            # Log body
                                            ft.Container(expand=True, content=log_body),
                                        ],
                                        spacing=0,
                                        expand=True,
                                    ),
                                    height=270,
                                ),
                            ),

                        ],
                    ),
                ),
            ],
        ),
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 2 — LIVE SITE  (WebView unsupported on Android in Flet 0.21)
    # ═══════════════════════════════════════════════════════════════════════════
    def _open_live_site(e):
        page.launch_url(LIVE_SITE_URL)

    live_tab = ft.Container(
        expand=True,
        bgcolor=BG_PAGE,
        content=ft.Column(
            expand=True,
            controls=[
                ft.Container(
                    bgcolor=WHITE,
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                    border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                    content=ft.Row(
                        [
                            icon_pill(ft.icons.LANGUAGE_OUTLINED,
                                      icon_size=15, padding_val=6),
                            ft.Text("nnnrc.com  ·  Live View", size=13,
                                    weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                ft.Container(
                    expand=True,
                    alignment=ft.alignment.center,
                    padding=ft.padding.symmetric(horizontal=32),
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=0,
                        controls=[
                            icon_pill(ft.icons.LANGUAGE_OUTLINED, icon_size=36,
                                      padding_val=18),
                            ft.Container(height=20),
                            ft.Text("nnnrc.com", size=20,
                                    weight=ft.FontWeight.W_700, color=TEXT_PRIMARY),
                            ft.Container(height=6),
                            ft.Text(
                                "View your tasks in your phone's browser.",
                                size=13, color=TEXT_SECONDARY,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(height=28),
                            ft.ElevatedButton(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.icons.OPEN_IN_BROWSER,
                                                color=WHITE, size=18),
                                        ft.Text("Open Live Site", size=14,
                                                weight=ft.FontWeight.W_600,
                                                color=WHITE),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                style=ft.ButtonStyle(
                                    shape=ft.RoundedRectangleBorder(radius=14),
                                    bgcolor={"": ACCENT, "hovered": "#15803D",
                                             "pressed": "#166534"},
                                    overlay_color="#FFFFFF18",
                                    elevation={"": 2, "hovered": 5},
                                    shadow_color="#16A34A30",
                                    padding=ft.padding.symmetric(
                                        horizontal=28, vertical=15),
                                ),
                                on_click=_open_live_site,
                            ),
                        ],
                    ),
                ),
            ],
            spacing=0,
        ),
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # TABS
    # ═══════════════════════════════════════════════════════════════════════════
    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=200,
        expand=True,
        tabs=[
            ft.Tab(text="Bot",       icon=ft.icons.SMART_TOY_OUTLINED,  content=bot_tab),
            ft.Tab(text="Live Site", icon=ft.icons.LANGUAGE_OUTLINED,   content=live_tab),
        ],
        indicator_color=ACCENT,
        label_color=ACCENT,
        unselected_label_color=TEXT_SECONDARY,
        divider_color=BORDER,
    )

    page.add(ft.SafeArea(tabs, expand=True))


if __name__ == "__main__":
    ft.app(target=main)
