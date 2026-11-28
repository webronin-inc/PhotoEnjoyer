"""Сценарий модуля Word (без интерфейса — окно только показывает ход и спрашивает).

    проверка Word → (подходит → запуск)
                  → данные об установщике → СОГЛАСИЕ → загрузка → проверка файла
                  → установка → повторная проверка → запуск

Установка и загрузка начинаются только после согласия пользователя; при отказе
ничего не скачивается и не запускается. Всё пишется в журнал.
"""
import traceback
from dataclasses import dataclass

from .detect import DEFAULT_MATCH
from .download import DownloadError
from .install import InstallError
from .package import PackageError

STEPS = (
    ("check", "Проверка Word"),
    ("package", "Данные об установщике"),
    ("consent", "Ваше согласие"),
    ("download", "Загрузка установщика"),
    ("verify", "Проверка файла"),
    ("install", "Установка Word 2021"),
    ("launch", "Запуск Word"),
)


@dataclass
class Outcome:
    kind: str                      # launched | declined | cancelled | error | reboot | unsupported
    message: str = ""
    detail: str = ""


class WordFlow:
    def __init__(self, *, detect, fetch, download, install, launch, ask, report, log,
                 track=lambda *a, **k: None, cancel=None, supported=True):
        self.detect, self.fetch, self.download = detect, fetch, download
        self.install, self.launch, self.ask = install, launch, ask
        self.report, self.log, self.track = report, log, track
        self.cancel = cancel
        self.supported = supported

    def run(self):
        log = self.log
        log.info("=== Модуль Word: запуск проверки ===")
        if not self.supported:
            log.info("Платформа не Windows — модуль недоступен")
            return Outcome("unsupported", "Модуль Word работает только в Windows.")
        try:
            return self._run()
        except PackageError as e:
            return self._fail("package", e.message, f"package:{e.code}")
        except DownloadError as e:
            if e.code == "cancelled":
                log.info("Загрузка отменена пользователем")
                self.report("download", "fail", "отменено")
                return Outcome("cancelled", "Загрузка отменена.")
            step = "verify" if e.code == "sha" else "download"
            return self._fail(step, e.message, f"download:{e.code}")
        except InstallError as e:
            return self._fail("install", e.message, f"install:{e.code}")
        except Exception as e:                      # непредвиденное — не роняем программу
            log.error("Непредвиденная ошибка:\n%s", traceback.format_exc())
            self.track("word_error", kind=type(e).__name__)
            return Outcome("error", "Что-то пошло не так. Подробности записаны в журнал.",
                           type(e).__name__)

    def _fail(self, step, message, detail):
        self.log.error("Ошибка [%s]: %s", detail, message)
        self.report(step, "fail", message[:60])
        self.track("word_error", kind=detail)
        return Outcome("error", message, detail)

    def _run(self):
        log, report = self.log, self.report

        report("check", "running")
        info = self.detect()
        log.info("Проверка Word: %s", info.as_log())
        ok_now = info.matches(DEFAULT_MATCH)
        self.track("word_check", match=ok_now, family=info.family or "none")
        if ok_now:
            report("check", "ok", info.describe())
            for s in ("package", "consent", "download", "verify", "install"):
                report(s, "skip")
            log.info("Word 2021 уже установлен — установка не требуется")
            return self._launch(info)
        report("check", "warn", info.describe())

        report("package", "running")
        pkg = self.fetch()
        log.info("Установщик на сервере: %s, %s, хост %s, sha256 %s…", pkg.filename,
                 pkg.size_text(), pkg.host, pkg.sha256[:12])
        report("package", "ok", f"{pkg.filename} · {pkg.size_text()}")
        if info.matches(pkg.match):                # сервер считает установленное подходящим
            log.info("Установленная версия подходит по правилам сервера (%s)", pkg.match)
            for s in ("consent", "download", "verify", "install"):
                report(s, "skip")
            return self._launch(info)

        report("consent", "running")
        ctx = {"target": pkg.target, "current": info.describe(), "installed": info.installed,
               "size_text": pkg.size_text(), "host": pkg.host, "notes": pkg.notes}
        log.info("Запрос согласия у пользователя (%s → %s)", info.describe(), pkg.target)
        if not self.ask(ctx):
            log.info("Пользователь отказался от установки — ничего не скачано и не запущено")
            report("consent", "fail", "отказ")
            self.track("word_declined")
            return Outcome("declined", "Установка отменена по вашему желанию.")
        log.info("Пользователь согласился на установку")
        report("consent", "ok")

        report("download", "running")
        self.track("word_download", size=pkg.size)
        path = self.download(pkg)
        log.info("Установщик скачан и проверен: %s", path)
        report("download", "ok")
        report("verify", "ok", "SHA-256 совпала")

        report("install", "running")
        self.track("word_install", file=pkg.filename)
        res = self.install(path, pkg)
        log.info("Установщик завершился: code=%s ok=%s reboot=%s — %s", res.code, res.ok,
                 res.reboot, res.message)
        if not res.ok:
            return self._fail("install", res.message, f"install:{res.code}")
        report("install", "ok", "перезагрузка не нужна" if not res.reboot else "нужна перезагрузка")

        info2 = self.detect()
        log.info("Повторная проверка: %s", info2.as_log())
        if info2.matches(pkg.match):
            return self._launch(info2)
        if res.reboot:
            return Outcome("reboot", "Установка завершена. Перезагрузите компьютер и запустите "
                           "Word снова.")
        return self._fail("install", "Установка завершилась, но Word 2021 не обнаружен. "
                          "Подробности — в журнале.", "not_detected")

    def _launch(self, info):
        self.report("launch", "running")
        self.launch(info)
        self.log.info("Word запущен: %s", info.exe_path or "winword")
        self.track("word_launch")
        self.report("launch", "ok")
        return Outcome("launched", "Word запущен.")
