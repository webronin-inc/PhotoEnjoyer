"""Движок анимаций: один общий таймер на все твины.

* В простое (нет активных анимаций) таймер не работает — CPU не тратится.
* Анимации можно отключить целиком (Настройки → «Анимации интерфейса»):
  тогда каждая анимация сразу выставляет конечное значение.
* Повторный запуск с тем же key отменяет предыдущую анимацию, поэтому
  быстрые наведения/уводы мыши не накапливаются.
"""
import math
import time


# ------------------------------------------------------------ функции плавности
def linear(t):
    return t


def ease_out_quad(t):
    return 1 - (1 - t) * (1 - t)


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t):
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def ease_out_back(t, s=1.70158):
    """Небольшой «перелёт» в конце — для эффекта пружинки."""
    t -= 1
    return 1 + t * t * ((s + 1) * t + s)


def ease_out_expo(t):
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------------- движок
class Animator:
    FRAME_MS = 16          # ~60 кадров/с

    def __init__(self, root, clock=time.monotonic):
        self.root = root
        self.enabled = True
        self._clock = clock
        self._tweens = []
        self._job = None
        self._errors = 0

    # ---------------------------------------------------------------- API
    def animate(self, duration_ms, on_update, on_done=None,
                easing=ease_out_cubic, key=None, delay_ms=0):
        """Запускает анимацию: on_update(p) вызывается с p от 0 до 1
        (уже со сглаживанием). Возвращает объект-ручку или None."""
        if key is not None:
            self.cancel(key)

        duration_ms = duration_ms * _SPEED.get(LEVEL, 1.0)
        if not self.enabled or duration_ms <= 0:
            # без анимации — сразу в конечное состояние
            self._safe_call(on_update, 1.0)
            if on_done:
                self._safe_call(on_done)
            return None

        tw = {
            "start": self._clock() + max(0, delay_ms) / 1000.0,
            "dur": duration_ms / 1000.0,
            "update": on_update,
            "done": on_done,
            "easing": easing,
            "key": key,
        }
        self._tweens.append(tw)
        self._ensure_running()
        return tw

    def cancel(self, key):
        """Отменяет анимацию(и) с этим key (без вызова on_done)."""
        self._tweens = [t for t in self._tweens if t["key"] != key]

    def stop_all(self, finish=False):
        """Останавливает все анимации. finish=True — выставить конечные значения."""
        tweens, self._tweens = self._tweens, []
        if finish:
            for t in tweens:
                self._safe_call(t["update"], 1.0)
                if t["done"]:
                    self._safe_call(t["done"])
        self._cancel_job()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            self.stop_all(finish=True)

    @property
    def active(self):
        return bool(self._tweens)

    # ---------------------------------------------------------- внутренности
    def _ensure_running(self):
        if self._job is None and self._tweens:
            try:
                self._job = self.root.after(self.FRAME_MS, self._tick)
            except Exception:
                self._job = None

    def _cancel_job(self):
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _safe_call(self, fn, *args):
        try:
            fn(*args)
            return True
        except Exception as e:
            # виджет мог быть уничтожен (смена темы, закрытие окна) — это норма
            if type(e).__name__ != "TclError":
                self._errors += 1
                if self._errors <= 5:
                    print(f"[anim] ошибка в анимации: {e!r}")
            return False

    def _tick(self):
        self._job = None
        now = self._clock()
        alive = []
        finished = []
        for tw in self._tweens:
            if now < tw["start"]:
                alive.append(tw)
                continue
            t = min(1.0, (now - tw["start"]) / tw["dur"])
            try:
                p = tw["easing"](t)
            except Exception:
                p = t
            ok = self._safe_call(tw["update"], p)
            if not ok:
                continue                       # виджет умер — снимаем твин
            if t >= 1.0:
                finished.append(tw)
            else:
                alive.append(tw)
        self._tweens = alive
        for tw in finished:
            if tw["done"]:
                self._safe_call(tw["done"])
        self._ensure_running()


# --------------------------------------------------------- общий экземпляр
_instances = {}
_default_enabled = True


def get(widget):
    """Возвращает Animator для окна, которому принадлежит виджет."""
    try:
        root = widget._root()
    except Exception:
        root = widget
    an = _instances.get(root)
    if an is None:
        an = Animator(root)
        an.enabled = _default_enabled
        _instances[root] = an
    return an


def set_enabled(enabled):
    """Включает/выключает анимации во всём приложении."""
    global _default_enabled
    _default_enabled = bool(enabled)
    for an in list(_instances.values()):
        an.set_enabled(enabled)


def is_enabled():
    return _default_enabled


# Уровни анимации: full — всё, soft — быстрее и без «эффектов» (частицы,
# рябь, конфетти), off — без анимаций (для слабых ПК и тех, кому мешает).
LEVELS = ("full", "soft", "off")
LEVEL = "full"
_SPEED = {"full": 1.0, "soft": 0.65, "off": 0.0}


def set_level(level):
    global LEVEL
    LEVEL = level if level in _SPEED else "full"
    set_enabled(LEVEL != "off")


def level():
    return LEVEL


def effects_enabled():
    """Декоративные эффекты (частицы, рябь, конфетти, неоновое мерцание)."""
    return LEVEL == "full" and _default_enabled


def tween_attr(widget, attr, target, duration=140, easing=ease_out_cubic,
               redraw=None):
    """Плавно меняет число widget.<attr> до target и вызывает redraw()."""
    start = float(getattr(widget, attr))
    redraw = redraw or getattr(widget, "_redraw", None)
    key = (id(widget), attr)
    if abs(start - target) < 1e-3:
        # Значение уже у цели, но может висеть ещё не начавшаяся анимация в
        # обратную сторону (быстрое Enter→Leave до первого тика): без отмены
        # она дойдёт до конца и подсветка «залипнет».
        get(widget).cancel(key)
        setattr(widget, attr, float(target))
        return

    def upd(p):
        setattr(widget, attr, start + (target - start) * p)
        if redraw:
            redraw()

    get(widget).animate(duration, upd, easing=easing, key=key)


def pulse_curve(t):
    """0→1→0 за один период (для «дыхания»)."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * t)
