"""Панель модуля Word внутри общего меню.

Сценарий работает в рабочем потоке (WordFlow), панель только показывает ход,
спрашивает согласие и итог. Сеть и установка никогда не блокируют интерфейс."""
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser

from .. import icons
from ..screens.login import _Steps
from ..ui_widgets import GradientButton, rounded_rect
from ..word import flow as wflow
from ..word import logs, service


def fmt_size(n):
    n = float(n)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} ГБ"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} МБ"
    return f"{n / 1024:.0f} КБ"


def fmt_eta(sec):
    sec = int(max(0, sec))
    if sec >= 3600:
        return f"{sec // 3600} ч {sec % 3600 // 60} мин"
    if sec >= 60:
        return f"{sec // 60} мин"
    return f"{sec} с"


class _Bar(tk.Canvas):
    def __init__(self, parent, p, width=560):
        super().__init__(parent, width=width, height=12, bg=p["surface"], highlightthickness=0)
        self.p, self._bw, self.value = p, width, 0.0
        self.indeterminate = False
        self._phase = 0.0
        self._job = None
        self.bind("<Destroy>", self._on_destroy, add="+")

    def set(self, v):
        self.value = max(0.0, min(1.0, v))
        self._draw()

    def start_indeterminate(self):
        self.indeterminate = True
        if self._job is None:
            self._spin()

    def stop_indeterminate(self):
        self.indeterminate = False
        self._draw()

    def _spin(self):
        self._job = None
        try:
            if not self.winfo_exists() or not self.indeterminate:
                return
            self._phase = (self._phase + 0.035) % 1.0
            self._draw()
            self._job = self.after(33, self._spin)
        except tk.TclError:
            pass

    def _on_destroy(self, event):
        if event.widget is self and self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _draw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        p, w = self.p, self._bw
        rounded_rect(self, 0, 1, w, 11, radius=5, fill=p["surface_alt"], outline="")
        col = icons.NEON["cyan"]
        if self.indeterminate:
            span = w * 0.28
            x0 = (w + span) * self._phase - span
            rounded_rect(self, max(0, x0), 1, min(w, x0 + span), 11, radius=5, fill=col, outline="")
        elif self.value > 0:
            rounded_rect(self, 0, 1, max(10, w * self.value), 11, radius=5, fill=col, outline="")


class WordPanel(tk.Frame):
    """on_back() вызывается при возврате в меню."""

    def __init__(self, parent, p, session, on_back, flow_factory=None, log=None):
        super().__init__(parent, bg=p["surface"], highlightthickness=1,
                         highlightbackground=p["border"])
        self.p, self.session, self.on_back = p, session, on_back
        self.flow_factory = flow_factory or service.make_flow
        self.log = log or logs.get_logger()
        self._q = queue.Queue()
        self._cancel = threading.Event()
        self._answer = None
        self._ask_event = None
        self._thread = None
        self._job = None
        self._running = False
        self._closed = False
        self._speed = (time.time(), 0)
        self._rate = 0.0
        self.outcome = None
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._build()

    def _build(self):
        p = self.p
        head = tk.Frame(self, bg=p["surface"])
        head.pack(fill=tk.X, padx=30, pady=(24, 6))
        ic = tk.Canvas(head, width=56, height=56, bg=p["surface"], highlightthickness=0)
        ic.pack(side=tk.LEFT)
        icons.draw_neon(ic, "word", 28, 28, size=30, color=icons.NEON["blue"])
        box = tk.Frame(head, bg=p["surface"])
        box.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(box, text="Microsoft Word", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(box, text="Проверка версии, установка Word 2021 и запуск", bg=p["surface"],
                 fg=p["text_dim"], font=("Segoe UI", 10)).pack(anchor="w")

        self.steps = _Steps(self, p, wflow.STEPS, width=560)
        self.steps.pack(padx=32, pady=(10, 0), anchor="w")

        self.prog = tk.Frame(self, bg=p["surface"])
        self.bar = _Bar(self.prog, p, 560)
        self.bar.pack(anchor="w")
        self.prog_text = tk.Label(self.prog, text="", bg=p["surface"], fg=p["text_dim"],
                                  font=("Segoe UI", 9), anchor="w")
        self.prog_text.pack(fill=tk.X, pady=(4, 0))

        self.msg = tk.Label(self, text="", bg=p["surface"], fg=p["text"], font=("Segoe UI", 11),
                            anchor="w", justify="left", wraplength=560)
        self.msg.pack(fill=tk.X, padx=32, pady=(10, 0))

        self.consent = tk.Frame(self, bg=p["surface_alt"], highlightthickness=1,
                                highlightbackground=p["border"])
        self.consent_title = tk.Label(self.consent, text="", bg=p["surface_alt"], fg=p["text"],
                                      font=("Segoe UI", 12, "bold"), anchor="w", justify="left",
                                      wraplength=520)
        self.consent_title.pack(fill=tk.X, padx=16, pady=(14, 4))
        self.consent_body = tk.Label(self.consent, text="", bg=p["surface_alt"], fg=p["text_dim"],
                                     font=("Segoe UI", 10), anchor="w", justify="left", wraplength=520)
        self.consent_body.pack(fill=tk.X, padx=16)
        crow = tk.Frame(self.consent, bg=p["surface_alt"])
        crow.pack(fill=tk.X, padx=16, pady=14)
        self.btn_yes = GradientButton(crow, p, text="Установить", icon="download", height=42,
                                      command=lambda: self._answer_consent(True))
        self.btn_yes.pack(side=tk.LEFT)
        self.btn_no = tk.Button(crow, text="Отмена", command=lambda: self._answer_consent(False),
                                bd=0, relief="flat", cursor="hand2", bg=p["surface"], fg=p["text"],
                                activebackground=p["surface_hi"], activeforeground=p["text"],
                                font=("Segoe UI", 10), padx=16, pady=9, highlightthickness=0,
                                takefocus=0)
        self.btn_no.pack(side=tk.LEFT, padx=(10, 0))

        self.actions = tk.Frame(self, bg=p["surface"])
        self.actions.pack(fill=tk.X, padx=32, pady=(14, 22), side=tk.BOTTOM)

    def _set_actions(self, *buttons):
        p = self.p
        for w in self.actions.winfo_children():
            w.destroy()
        for text, cmd, primary in buttons:
            if primary:
                b = GradientButton(self.actions, p, text=text, icon="refresh", height=40, command=cmd)
            else:
                b = tk.Button(self.actions, text=text, command=cmd, bd=0, relief="flat",
                              cursor="hand2", bg=p["surface_alt"], fg=p["text"],
                              activebackground=p["surface_hi"], activeforeground=p["text"],
                              font=("Segoe UI", 10), padx=16, pady=9, highlightthickness=0,
                              takefocus=0)
            b.pack(side=tk.LEFT, padx=(0, 10))

    def start(self):
        self._running = True
        self._cancel = threading.Event()
        self.outcome = None
        self.steps.reset()
        self.msg.configure(text="", fg=self.p["text"])
        self.consent.pack_forget()
        self.prog.pack_forget()
        self._set_actions()
        q = self._q

        def report(step, state, detail=""):
            q.put(("step", step, state, detail))

        last = [0.0]

        def progress(stage, done, total):
            now = time.time()
            if now - last[0] < 0.1 and done < total:
                return
            last[0] = now
            q.put(("progress", stage, done, total))

        flow = self.flow_factory(self.session, self._ask_from_thread, report, progress,
                                 self._cancel, log=self.log)

        def work():
            try:
                q.put(("done", flow.run()))
            except Exception as e:
                self.log.exception("Сбой сценария Word")
                q.put(("done", wflow.Outcome("error", "Что-то пошло не так. Подробности — в журнале.",
                                             type(e).__name__)))
        self._thread = threading.Thread(target=work, daemon=True, name="word-flow")
        self._thread.start()
        self._poll()

    def _ask_from_thread(self, ctx):
        ev = threading.Event()
        self._q.put(("ask", ctx, ev))
        while not ev.wait(0.5):
            if self._closed:
                return False
        return bool(self._answer)

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, *rest = self._q.get_nowait()
                if kind == "step":
                    self._on_step(*rest)
                elif kind == "progress":
                    self._on_progress(*rest)
                elif kind == "ask":
                    self._on_ask(*rest)
                elif kind == "done":
                    return self._on_done(rest[0])
        except queue.Empty:
            pass
        self._job = self.after(40, self._poll)

    def _on_step(self, step, state, detail):
        self.steps.set(step, state, detail)
        if step == "download" and state == "running":
            self.prog.pack(padx=32, pady=(6, 0), anchor="w", after=self.steps)
            self.bar.stop_indeterminate()
            self.bar.set(0.0)
            self.prog_text.configure(text="Подключаемся к серверу…")
            self._speed = (time.time(), 0)
            self._set_actions(("Отменить загрузку", self._cancel_download, False))
        elif step == "install" and state == "running":
            self.prog.pack(padx=32, pady=(6, 0), anchor="w", after=self.steps)
            self.bar.start_indeterminate()
            self.prog_text.configure(text="Идёт установка — это может занять несколько минут. "
                                          "Окно закрывать не нужно.")
            self._set_actions()
        elif step in ("install", "launch") and state in ("ok", "fail"):
            self.bar.stop_indeterminate()

    def _on_progress(self, stage, done, total):
        total = max(total, 1)
        if stage == "download":
            now = time.time()
            t0, d0 = self._speed
            if now - t0 >= 0.8:
                self._speed = (now, done)
                self._rate = (done - d0) / max(now - t0, 0.001)
            rate = self._rate
            eta = (total - done) / rate if rate > 0 else 0
            self.bar.set(done / total)
            self.prog_text.configure(
                text=f"{fmt_size(done)} из {fmt_size(total)}"
                     + (f"  ·  {fmt_size(rate)}/с  ·  осталось {fmt_eta(eta)}" if rate > 0 else ""))
        else:
            self.bar.set(done / total)
            self.prog_text.configure(text=f"Проверяем целостность файла… {int(100 * done / total)}%")

    def _on_ask(self, ctx, ev):
        self._ask_event = ev
        self.steps.set("consent", "running")
        self.consent_title.configure(
            text=f"Установить {ctx['target']}?" if not ctx["installed"]
            else f"Обновить Word до версии {ctx['target']}?")
        self.consent_body.configure(text=(
            f"Сейчас: {ctx['current']}.\n"
            f"Установщик ({ctx['size_text']}) будет скачан с вашего сервера ({ctx['host']}), "
            f"проверен по контрольной сумме и запущен от имени администратора.\n"
            f"Нужен действующий лицензионный ключ Microsoft Office."
            + (f"\n{ctx['notes']}" if ctx.get("notes") else "")))
        self.consent.pack(fill=tk.X, padx=32, pady=(12, 0), before=self.actions)
        self.btn_yes.focus_set()

    def _answer_consent(self, yes):
        self._answer = bool(yes)
        self.consent.pack_forget()
        ev = self._ask_event
        if ev is not None:
            ev.set()

    def _cancel_download(self):
        self._cancel.set()
        self.prog_text.configure(text="Отменяем…")

    def _on_done(self, out):
        self._running = False
        self.outcome = out
        self.bar.stop_indeterminate()
        self.prog.pack_forget()
        self.consent.pack_forget()
        colors = {"launched": icons.NEON["lime"], "declined": self.p["text_dim"],
                  "cancelled": self.p["text_dim"], "reboot": icons.NEON["orange"],
                  "unsupported": icons.NEON["orange"], "error": icons.NEON["red"]}
        self.msg.configure(text=out.message, fg=colors.get(out.kind, self.p["text"]))
        buttons = []
        if out.kind in ("error", "cancelled"):
            buttons.append(("Повторить", self.start, True))
        if out.kind in ("error", "reboot"):
            buttons.append(("Открыть журнал", self.open_log, False))
        buttons.append(("Назад в меню", self.on_back, False))
        self._set_actions(*buttons)

    def open_log(self):
        path = logs.log_path_in_use()
        try:
            if sys.platform == "win32":
                os.startfile(str(path))          # noqa: S606
            else:
                webbrowser.open(path.as_uri())
        except Exception:
            pass

    def _on_destroy(self, event):
        if event.widget is self:
            self._closed = True
            self._cancel.set()
            ev = self._ask_event
            if ev is not None:
                ev.set()
            if self._job is not None:
                try:
                    self.after_cancel(self._job)
                except Exception:
                    pass
                self._job = None
