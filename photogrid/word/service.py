"""Сборка «боевого» сценария Word из реальных деталей (реестр, сеть, запуск)."""
import os
import subprocess
import sys
import threading

from ..account import gate
from . import detect as _detect
from . import download as _download
from . import install as _install
from .flow import WordFlow
from .logs import get_logger
from .package import PackageError, fetch_package


def launch_word(info):
    if sys.platform != "win32":
        raise RuntimeError("запуск Word возможен только в Windows")
    exe = info.exe_path
    if exe:
        os.startfile(exe)                           # noqa: S606 — штатный запуск файла
    else:
        subprocess.Popen(["cmd", "/c", "start", "", "winword.exe"], shell=False)


def make_flow(session, ask, report, progress, cancel=None, track=None, log=None, *,
              reader=None, pub=None, supported=None, runner=subprocess.run, admin=None,
              file_exists=os.path.exists):
    log = log or get_logger()
    track = track or (session.track if session is not None else (lambda *a, **k: None))
    supported = (sys.platform == "win32") if supported is None else supported
    cancel = cancel or threading.Event()

    def fetch():
        if session is None:
            raise PackageError("no_server", "Сервер не настроен — установщик получить нельзя.")
        return fetch_package(session.api, pub or gate.public_key())

    def download(pkg):
        return _download.download(pkg.url, _install.work_dir(), pkg.filename, pkg.sha256,
                                  pkg.size, progress, cancel)

    def install(path, pkg):
        folder = _install.work_dir()
        cfg = _install.write_config(pkg, folder)
        cmd = _install.build_command(path, pkg, cfg)
        log.info("Запуск установщика: %s", " ".join(cmd)[:300])
        code = _install.run_installer(cmd, admin=admin, runner=runner)
        return _install.interpret(code)

    return WordFlow(detect=lambda: _detect.detect_word(reader, file_exists), fetch=fetch,
                    download=download, install=install, launch=launch_word, ask=ask,
                    report=report, log=log, track=track, cancel=cancel, supported=supported)
