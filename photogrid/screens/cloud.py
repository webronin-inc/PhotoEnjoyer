"""Экран «Облако». Пока — заглушка с описанием; полноценный экран появится
вместе с аккаунтами (облако привязано к личному кабинету)."""
import tkinter as tk

from .. import anim, icons
from ..ui_widgets import _blend_hex


def build_cloud_view(parent, app):
    p = app.palette
    root = tk.Frame(parent, bg=p["bg"])

    card = tk.Frame(root, bg=p["surface"], highlightthickness=1,
                    highlightbackground=p["border"])
    card.pack(expand=True)
    inner = tk.Frame(card, bg=p["surface"])
    inner.pack(padx=60, pady=44)

    cv = tk.Canvas(inner, width=140, height=120, bg=p["surface"],
                   highlightthickness=0)
    cv.pack()
    state = {"phase": 0.0, "job": None}

    def draw(glow):
        cv.delete("all")
        icons.draw_neon(cv, "cloud", 70, 62, size=64,
                        color=icons.NEON["blue"], glow=glow)

    def tick():
        state["job"] = None
        try:
            if not cv.winfo_exists():
                return
            if cv.winfo_ismapped() and anim.effects_enabled():
                state["phase"] = (state["phase"] + 0.02) % 1.0
                draw(round((0.5 + 0.75 * anim.pulse_curve(state["phase"])) * 4) / 4)
            state["job"] = cv.after(90, tick)
        except tk.TclError:
            pass

    draw(1.0)
    state["job"] = cv.after(300, tick)

    tk.Label(inner, text="Облако PhotoEnjoyer", bg=p["surface"], fg=p["text"],
             font=("Segoe UI", 20, "bold")).pack(pady=(10, 4))
    tk.Label(inner, text="Храните проекты и готовые коллажи онлайн,\n"
                         "открывайте их на любом компьютере и делитесь ссылкой.",
             bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 11),
             justify="center").pack()
    chip = tk.Label(inner, text="  Скоро — вместе с личным кабинетом  ",
                    bg=_blend_hex(p["accent"], p["surface"], 0.22),
                    fg=p["accent_hi"], font=("Segoe UI", 9, "bold"), pady=5)
    chip.pack(pady=(18, 0))
    return root
