"""Общие настройки pytest.

В GitHub Actions упавшие тесты дополнительно выводятся как аннотации
(::error ...) — их видно прямо в интерфейсе запуска и через API проверок,
без скачивания полного лога.
"""
import os


def _esc(text):
    return (str(text).replace("%", "%25").replace("\r", "%0D")
            .replace("\n", "%0A"))


def pytest_runtest_logreport(report):
    if not os.environ.get("GITHUB_ACTIONS") or not report.failed:
        return
    crash = getattr(report.longrepr, "reprcrash", None)
    msg = crash.message if crash else str(report.longrepr)
    where = f"{report.location[0]}:{report.location[1] + 1}"
    print(f"\n::error title={_esc('pytest: ' + report.nodeid)}::"
          f"{_esc((where + ' ' + msg)[:1500])}")
