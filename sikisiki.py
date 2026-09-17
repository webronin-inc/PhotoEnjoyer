"""PhotoGrid — точка входа. Весь код живёт в пакете photogrid."""
import sys

# DPI awareness — ДО импорта tkinter
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# UTF-8 для stdout/stderr — чтобы print с "✓"/"✗"/кириллицей
# не падал на русской Windows (cp1251/cp866)
for _stream in ("stdout", "stderr"):
    _s = getattr(sys, _stream, None)
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from photogrid.app import run

if __name__ == "__main__":
    run()