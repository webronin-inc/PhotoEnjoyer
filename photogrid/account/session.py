"""Сессия пользователя и отправка событий использования."""
import threading
import time

from .api import ApiError, NetworkError


class Session:
    """Данные вошедшего пользователя + доступ к серверу."""

    def __init__(self, api, token, info, offline=False):
        self.api = api
        self.token = token
        api.token = token
        self.offline = offline
        self.info = info or {}
        self.telemetry = Telemetry(self)

    # ---- данные профиля
    @property
    def username(self):
        return self.info.get("user", {}).get("username", "")

    @property
    def role(self):
        return self.info.get("user", {}).get("role", "user")

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def license(self):
        return self.info.get("license", {})

    @property
    def license_state(self):
        return self.license.get("state", "none")

    @property
    def license_active(self):
        return self.license_state == "active"

    @property
    def devices(self):
        return self.info.get("devices", [])

    @property
    def usage_stats(self):
        return bool(self.info.get("user", {}).get("usage_stats", True))

    @property
    def must_change_pw(self):
        return bool(self.info.get("user", {}).get("must_change_pw"))

    def days_left(self, now=None):
        """Сколько дней осталось (None — бессрочно, 0 — истекает/истекла)."""
        exp = self.license.get("expires")
        if exp is None:
            return None
        return max(0, int((exp - (now or time.time())) // 86400))

    def apply(self, resp):
        """Обновить данные из ответа сервера (login/refresh/activate-key)."""
        if resp.get("token"):
            self.token = resp["token"]
            self.api.token = self.token
        for k in ("user", "license", "devices"):
            if k in resp:
                self.info[k] = resp[k]

    # ---- действия
    def track(self, event, **data):
        self.telemetry.track(event, **data)

    def close(self):
        self.telemetry.stop()


class Telemetry:
    """Копит события и отправляет пачками в фоне. Никогда не мешает работе:
    все ошибки сети проглатываются, очередь ограничена."""

    MAX_QUEUE = 200
    ESSENTIAL = {"app_start", "app_exit", "error"}

    def __init__(self, session, interval=45.0):
        self.session = session
        self.interval = interval
        self._q = []
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._thread = None

    def start(self):
        if self._thread is None and not self.session.offline:
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="telemetry")
            self._thread.start()

    def track(self, event, **data):
        if event not in self.ESSENTIAL and not self.session.usage_stats:
            return
        with self._lock:
            self._q.append({"t": event, "d": data or None, "ts": int(time.time())})
            del self._q[:-self.MAX_QUEUE]
            big = len(self._q) >= 12
        if big:
            self._wake.set()

    def _take(self):
        with self._lock:
            batch, self._q = self._q[:50], self._q[50:]
        return batch

    def flush(self):
        """Отправить накопленное (синхронно). True — всё ушло."""
        if self.session.offline:
            return False
        batch = self._take()
        while batch:
            try:
                self.session.api.send_events(batch)
            except (NetworkError, ApiError):
                with self._lock:                  # вернём в очередь для следующей попытки
                    self._q = (batch + self._q)[-self.MAX_QUEUE:]
                return False
            batch = self._take()
        return True

    def _loop(self):
        while not self._stop:
            self._wake.wait(self.interval)
            self._wake.clear()
            if self._stop:
                break
            self.flush()

    def stop(self):
        self._stop = True
        self._wake.set()
        try:
            self.flush()
        except Exception:
            pass
