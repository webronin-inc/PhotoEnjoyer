"""Общие настройки pytest.

В GitHub Actions упавшие тесты дополнительно выводятся как аннотации
(::error ...) — их видно прямо в интерфейсе запуска и через API проверок,
без скачивания полного лога.
"""
import os


def _esc(text):
    return (str(text).replace("%", "%25").replace("\r", "%0D")
            .replace("\n", "%0A"))


def pytest_terminal_summary(terminalreporter):
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for kind in ("failed", "error"):
        for rep in terminalreporter.stats.get(kind, []):
            crash = getattr(rep.longrepr, "reprcrash", None)
            msg = crash.message if crash else str(rep.longrepr)
            where = f"{rep.location[0]}:{rep.location[1] + 1}"
            terminalreporter.write_line(
                f"::error title={_esc('pytest: ' + rep.nodeid)}::"
                f"{_esc((where + ' ' + msg)[:1500])}")
