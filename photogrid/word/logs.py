"""Журнал модуля Word: проверка, скачивание и установка пишутся в файл."""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

_NAME = "photoenjoyer.word"


def default_log_path():
    base = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None
    root = Path(base) if base else Path.home()
    return root / "PhotoEnjoyer" / "logs" / "word.log"


def get_logger(path=None):
    """Логгер модуля; файл с ротацией (1 МБ × 3). Повторный вызов не плодит обработчики."""
    log = logging.getLogger(_NAME)
    log.setLevel(logging.INFO)
    log.propagate = False
    target = Path(path) if path else default_log_path()
    for h in log.handlers:
        if getattr(h, "_pe_path", None) == str(target):
            return log
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3,
                                                 encoding="utf-8")
        h._pe_path = str(target)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                         "%Y-%m-%d %H:%M:%S"))
        log.addHandler(h)
    except OSError:
        log.addHandler(logging.NullHandler())      # журнал не должен ронять программу
    return log


def log_path_in_use():
    for h in logging.getLogger(_NAME).handlers:
        p = getattr(h, "_pe_path", None)
        if p:
            return Path(p)
    return default_log_path()
