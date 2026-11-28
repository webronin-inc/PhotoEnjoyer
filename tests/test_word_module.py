"""Модуль Word: определение версии, подписанное описание, загрузка, установка, сценарий."""
import hashlib
import http.server
import logging
import socketserver
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("cryptography")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server import security                                    # noqa: E402
from photogrid.account.api import ApiError, NetworkError        # noqa: E402
from photogrid.word import detect, download, install, logs      # noqa: E402
from photogrid.word.flow import Outcome, WordFlow               # noqa: E402
from photogrid.word.package import (Package, PackageError, fetch_package,  # noqa: E402
                                     parse_manifest)


class FakeReg:
    def __init__(self, values=None, keys=()):
        self.values, self.keys = values or {}, set(keys)

    def get(self, path, name=""):
        return self.values.get((path, name))

    def key_exists(self, path):
        return path in self.keys


def c2r(ids, version="16.0.14332.20000", platform="x64", exe=r"C:\Office\WINWORD.EXE"):
    return FakeReg({(detect.C2R, "ProductReleaseIds"): ids, (detect.C2R, "VersionToReport"): version,
                    (detect.C2R, "Platform"): platform, (detect.APP_PATH, ""): exe})


@pytest.mark.parametrize("ids,family,match", [
    ("ProPlus2021Volume", "2021", True),
    ("Word2021Retail,Excel2021Retail", "2021", True),
    ("Standard2021Volume", "2021", True),
    ("HomeStudent2021Retail", "2021", True),
    ("O365ProPlusRetail", "Microsoft 365", False),
    ("ProPlus2019Volume", "2019", False),
    ("ProPlus2024Volume", "2024", False),
    ("ProPlusRetail,Visio2021Volume", "2021", True),
])
def test_detect_families_and_2021_match(ids, family, match):
    info = detect.detect_word(c2r(ids), file_exists=lambda p: True)
    assert info.installed and info.family == family and info.matches() is match


def test_not_installed():
    info = detect.detect_word(FakeReg(), file_exists=lambda p: False)
    assert not info.installed and not info.matches() and "не найден" in info.describe()


def test_registry_path_without_file_is_not_installed():
    info = detect.detect_word(FakeReg({(detect.APP_PATH, ""): r"C:\gone\WINWORD.EXE"}),
                              file_exists=lambda p: False)
    assert not info.installed and info.notes


def test_msi_installs_are_never_2021():
    reg = FakeReg({(detect.APP_PATH, ""): r"C:\Office16\WINWORD.EXE"},
                  keys=[r"SOFTWARE\Microsoft\Office\16.0\Word\InstallRoot"])
    info = detect.detect_word(reg, file_exists=lambda p: True)
    assert info.installed and info.family == "2016" and not info.matches()


def test_detect_describe_mentions_build_and_logline_is_complete():
    info = detect.detect_word(c2r("ProPlus2021Volume", "16.0.14332.20500"), file_exists=lambda p: True)
    assert "2021" in info.describe() and "14332" in info.describe()
    assert "ids=ProPlus2021Volume" in info.as_log() and "platform=x64" in info.as_log()


def test_match_patterns_come_from_server_rules():
    info = detect.detect_word(c2r("ProPlus2024Volume"), file_exists=lambda p: True)
    assert not info.matches(("2021",)) and info.matches(("2024",))


def test_real_registry_reader_is_safe_on_any_platform():
    info = detect.detect_word()
    assert isinstance(info.installed, bool)


@pytest.fixture
def keypair(tmp_path):
    priv = security.load_or_create_keypair(str(tmp_path / "k"))
    return priv, priv.public_key()


def manifest(priv, **over):
    pkg = {"enabled": True, "target": "Word 2021", "match": ["2021"],
           "url": "https://files.example.com/setup.exe", "sha256": "ab" * 32, "size": 1234,
           "filename": "setup.exe", "args": ["/configure", "{config}"], "config_xml": "<x/>",
           "notes": ""}
    pkg.update(over)
    now = int(time.time())
    return security.sign_token(priv, {"v": 1, "kind": "word", "iat": now, "exp": now + 600, "pkg": pkg})


def test_manifest_roundtrip(keypair):
    priv, pub = keypair
    p = parse_manifest(manifest(priv), pub)
    assert p.filename == "setup.exe" and p.host == "files.example.com" and p.args[0] == "/configure"
    assert p.size_text() == "1 МБ"


@pytest.mark.parametrize("over", [
    {"url": "http://evil.example.com/setup.exe"}, {"sha256": "nothex"}, {"filename": "..\\x.exe"},
    {"filename": "run.bat"}, {"enabled": False}, {"url": ""},
])
def test_manifest_rejects_unsafe_content_even_if_signed(keypair, over):
    priv, pub = keypair
    with pytest.raises(PackageError) as e:
        parse_manifest(manifest(priv, **over), pub)
    assert e.value.code == "bad_manifest"


def test_manifest_rejects_forgery_wrong_key_and_expiry(keypair, tmp_path):
    priv, pub = keypair
    stranger = security.load_or_create_keypair(str(tmp_path / "other"))
    with pytest.raises(PackageError):
        parse_manifest(manifest(stranger), pub)
    tok = manifest(priv)
    with pytest.raises(PackageError):
        parse_manifest(tok, pub, now=time.time() + 3600)
    head, sig = tok.split(".")
    with pytest.raises(PackageError):
        parse_manifest(head + "A." + sig, pub)


def test_localhost_http_is_allowed_for_debug(keypair):
    priv, pub = keypair
    assert parse_manifest(manifest(priv, url="http://127.0.0.1:9/setup.exe"), pub).host == "127.0.0.1"


class FakeApi:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc = resp, exc

    def software_word(self):
        if self.exc:
            raise self.exc
        return self.resp


def test_fetch_package_error_mapping(keypair):
    priv, pub = keypair
    assert fetch_package(FakeApi({"manifest": manifest(priv)}), pub).sha256 == "ab" * 32
    for exc, code in ((NetworkError("x"), "network"),
                      (ApiError(404, "not_configured", "нет"), "not_configured"),
                      (ApiError(403, "license_expired", "x"), "license")):
        with pytest.raises(PackageError) as e:
            fetch_package(FakeApi(exc=exc), pub)
        assert e.value.code == code


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b""
    support_range = True
    fail_after = None
    hits = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        type(self).hits.append(rng)
        data = self.payload
        start = 0
        if rng and self.support_range:
            start = int(rng.split("=")[1].split("-")[0])
            if start >= len(data):
                self.send_response(416); self.end_headers(); return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.fail_after is not None:
            self.wfile.write(body[: self.fail_after])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(body)


@pytest.fixture
def filehost():
    class H(_Handler):
        pass
    H.payload = (b"0123456789abcdef" * 40000)
    H.hits = []
    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    srv.allow_reuse_address = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.url = f"http://127.0.0.1:{srv.server_address[1]}/setup.exe"
    H.sha = hashlib.sha256(H.payload).hexdigest()
    yield H
    srv.shutdown(); srv.server_close()


def test_download_ok_with_progress_and_verification(filehost, tmp_path):
    seen = []
    p = download.download(filehost.url, tmp_path, "setup.exe", filehost.sha, len(filehost.payload),
                          progress=lambda st, d, t: seen.append((st, d, t)))
    assert p.read_bytes() == filehost.payload and not (tmp_path / "setup.exe.part").exists()
    assert seen[0][0] == "download" and seen[-1][0] == "verify" and seen[-1][1] == seen[-1][2]


def test_download_wrong_hash_deletes_file_and_refuses(filehost, tmp_path):
    with pytest.raises(download.DownloadError) as e:
        download.download(filehost.url, tmp_path, "setup.exe", "0" * 64, len(filehost.payload))
    assert e.value.code == "sha"
    assert not (tmp_path / "setup.exe").exists() and not (tmp_path / "setup.exe.part").exists()


def test_download_resumes_after_interruption(filehost, tmp_path):
    filehost.fail_after = 100_000
    with pytest.raises(download.DownloadError) as e:
        download.download(filehost.url, tmp_path, "setup.exe", filehost.sha, len(filehost.payload))
    assert e.value.code in ("size", "network")
    part = tmp_path / "setup.exe.part"
    assert 0 < part.stat().st_size < len(filehost.payload)
    filehost.fail_after = None
    p = download.download(filehost.url, tmp_path, "setup.exe", filehost.sha, len(filehost.payload))
    assert p.read_bytes() == filehost.payload
    assert any(h and h.startswith("bytes=") for h in filehost.hits)


def test_download_restarts_when_server_has_no_range_support(filehost, tmp_path):
    filehost.support_range = False
    (tmp_path / "setup.exe.part").write_bytes(filehost.payload[:5000])
    p = download.download(filehost.url, tmp_path, "setup.exe", filehost.sha, len(filehost.payload))
    assert p.read_bytes() == filehost.payload


def test_download_reuses_valid_file_without_network(tmp_path):
    f = tmp_path / "setup.exe"; f.write_bytes(b"abc")
    p = download.download("http://127.0.0.1:9/x.exe", tmp_path, "setup.exe",
                          hashlib.sha256(b"abc").hexdigest(), 3)
    assert p == f


def test_download_cancel_and_network_down(filehost, tmp_path):
    ev = threading.Event(); ev.set()
    with pytest.raises(download.DownloadError) as e:
        download.download(filehost.url, tmp_path, "setup.exe", filehost.sha, len(filehost.payload), cancel=ev)
    assert e.value.code == "cancelled"
    with pytest.raises(download.DownloadError) as e:
        download.download("http://127.0.0.1:9/x.exe", tmp_path / "n", "x.exe", "0" * 64, 10, timeout=1)
    assert e.value.code == "network"


def test_download_refuses_when_disk_is_too_small(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "enough_space", lambda d, n: False)
    with pytest.raises(download.DownloadError) as e:
        download.download("http://127.0.0.1:9/x.exe", tmp_path, "x.exe", "0" * 64, 10 ** 9)
    assert e.value.code == "space"


def pkg(**kw):
    base = dict(url="https://h/x.exe", sha256="ab" * 32, filename="setup.exe",
                args=["/configure", "{config}"], config_xml="<Configuration/>")
    base.update(kw)
    return Package(**base)


def test_build_command_exe_msi_and_placeholders(tmp_path):
    cfg = tmp_path / "configuration.xml"
    assert install.build_command(tmp_path / "setup.exe", pkg(), cfg) == [str(tmp_path / "setup.exe"), "/configure", str(cfg)]
    assert install.build_command(tmp_path / "w.msi", pkg(args=[]), None)[:3] == ["msiexec", "/i", str(tmp_path / "w.msi")]
    assert install.build_command(tmp_path / "w.msi", pkg(args=[]), None)[-2:] == ["/qn", "/norestart"]


def test_config_file_written_only_when_present(tmp_path):
    assert install.write_config(pkg(), tmp_path).read_text(encoding="utf-8") == "<Configuration/>"
    assert install.write_config(pkg(config_xml="  "), tmp_path) is None


def test_exit_code_interpretation():
    assert install.interpret(0).ok and not install.interpret(0).reboot
    r = install.interpret(3010)
    assert r.ok and r.reboot
    for code in (1223, 1602, 1618, 1603, 5):
        res = install.interpret(code)
        assert not res.ok and res.message
    assert "администратора" in install.interpret(1223).message


def test_elevation_wrapper_quotes_arguments_safely():
    cmd = install.elevated_command([r"C:\Dir With Space\setup.exe", "/configure", "it's.xml"])
    script = cmd[-1]
    assert cmd[0] == "powershell" and "-Verb RunAs" in script and "-Wait -PassThru" in script
    assert "'it''s.xml'" in script and "catch { exit 1223 }" in script


def test_run_installer_uses_elevation_only_when_not_admin():
    calls = []

    class R:
        returncode = 0
    runner = lambda cmd, **kw: calls.append(cmd) or R()
    install.run_installer(["setup.exe", "/x"], admin=True, runner=runner)
    install.run_installer(["setup.exe", "/x"], admin=False, runner=runner)
    assert calls[0] == ["setup.exe", "/x"] and calls[1][0] == "powershell"


def test_run_installer_reports_missing_file():
    def boom(cmd, **kw):
        raise FileNotFoundError()
    with pytest.raises(install.InstallError):
        install.run_installer(["nope.exe"], admin=True, runner=boom)


def test_log_file_records_and_does_not_duplicate_handlers(tmp_path):
    path = tmp_path / "logs" / "word.log"
    log = logs.get_logger(path)
    log.info("Проверка Word: тест")
    logs.get_logger(path).info("ещё строка")
    for h in log.handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "Проверка Word: тест" in text and text.count("ещё строка") == 1
    assert logs.log_path_in_use() == path
    logging.getLogger("photoenjoyer.word").handlers.clear()


class Harness:
    def __init__(self, tmp_path, info, pkg_=None, consent=True, fetch_exc=None, dl_exc=None,
                 install_result=None, info_after=None):
        self.calls, self.reports, self.events = [], [], []
        self.infos = [info] + ([info_after] if info_after is not None else [])
        self.consent, self.fetch_exc, self.dl_exc = consent, fetch_exc, dl_exc
        self.pkg = pkg_ or pkg(match=("2021",))
        self.install_result = install_result or install.InstallResult(True, False, 0, "ok")
        log = logs.get_logger(tmp_path / "flow.log")
        self.flow = WordFlow(detect=self._detect, fetch=self._fetch, download=self._download,
                             install=self._install, launch=self._launch, ask=self._ask,
                             report=lambda s, st, d="": self.reports.append((s, st)),
                             log=log, track=lambda e, **k: self.events.append(e))

    def _detect(self):
        self.calls.append("detect")
        return self.infos.pop(0) if len(self.infos) > 1 else self.infos[0]

    def _fetch(self):
        self.calls.append("fetch")
        if self.fetch_exc:
            raise self.fetch_exc
        return self.pkg

    def _ask(self, ctx):
        self.calls.append("ask")
        self.ctx = ctx
        return self.consent

    def _download(self, p):
        self.calls.append("download")
        if self.dl_exc:
            raise self.dl_exc
        return Path("setup.exe")

    def _install(self, path, p):
        self.calls.append("install")
        return self.install_result

    def _launch(self, info):
        self.calls.append("launch")

    def run(self):
        return self.flow.run()


def info(ids, exe=True):
    return detect.detect_word(c2r(ids), file_exists=lambda p: exe)


def test_flow_already_2021_launches_without_network_or_consent(tmp_path):
    h = Harness(tmp_path, info("ProPlus2021Volume"))
    out = h.run()
    assert out.kind == "launched" and h.calls == ["detect", "launch"]
    assert "word_check" in h.events and "word_launch" in h.events


def test_flow_outdated_word_asks_consent_then_installs_then_launches(tmp_path):
    h = Harness(tmp_path, info("ProPlus2019Volume"), info_after=info("ProPlus2021Volume"))
    out = h.run()
    assert out.kind == "launched"
    assert h.calls == ["detect", "fetch", "ask", "download", "install", "detect", "launch"]
    assert h.ctx["target"] == "Word 2021" and "2019" in h.ctx["current"]
    assert ("download", "ok") in h.reports and ("install", "ok") in h.reports


def test_flow_no_word_at_all_also_asks(tmp_path):
    h = Harness(tmp_path, info("", exe=False), info_after=info("ProPlus2021Volume"))
    assert h.run().kind == "launched" and "ask" in h.calls and "не найден" in h.ctx["current"]


def test_flow_declined_downloads_and_installs_nothing(tmp_path):
    h = Harness(tmp_path, info("O365ProPlusRetail"), consent=False)
    out = h.run()
    assert out.kind == "declined"
    assert "download" not in h.calls and "install" not in h.calls and "launch" not in h.calls
    assert "word_declined" in h.events
    assert "отказался" in (tmp_path / "flow.log").read_text(encoding="utf-8")


def test_flow_server_rules_can_accept_installed_version(tmp_path):
    h = Harness(tmp_path, info("ProPlus2024Volume"), pkg_=pkg(match=("2024",)))
    assert h.run().kind == "launched" and "ask" not in h.calls and "download" not in h.calls


def test_flow_install_failure_is_reported_friendly(tmp_path):
    h = Harness(tmp_path, info("ProPlus2019Volume"),
                install_result=install.InstallResult(False, False, 1618, "Уже идёт другая установка."))
    out = h.run()
    assert out.kind == "error" and "другая установка" in out.message and "launch" not in h.calls


def test_flow_installed_but_not_detected(tmp_path):
    h = Harness(tmp_path, info("ProPlus2019Volume"), info_after=info("ProPlus2019Volume"))
    out = h.run()
    assert out.kind == "error" and out.detail == "not_detected"


def test_flow_reboot_required(tmp_path):
    h = Harness(tmp_path, info("ProPlus2019Volume"), info_after=info("ProPlus2019Volume"),
                install_result=install.InstallResult(True, True, 3010, "reboot"))
    out = h.run()
    assert out.kind == "reboot" and "Перезагрузите" in out.message


@pytest.mark.parametrize("exc,expect_kind,text", [
    (PackageError("not_configured", "Установщик Word ещё не загружен на сервер."), "error", "не загружен"),
    (PackageError("network", "Нет связи с сервером."), "error", "связи"),
])
def test_flow_package_errors(tmp_path, exc, expect_kind, text):
    h = Harness(tmp_path, info("ProPlus2019Volume"), fetch_exc=exc)
    out = h.run()
    assert out.kind == expect_kind and text in out.message and "ask" not in h.calls
    assert "word_error" in h.events


def test_flow_download_errors_and_cancel(tmp_path):
    h = Harness(tmp_path, info("ProPlus2019Volume"),
                dl_exc=download.DownloadError("sha", "Контрольная сумма не совпала"))
    out = h.run()
    assert out.kind == "error" and "install" not in h.calls and ("verify", "fail") in h.reports
    h2 = Harness(tmp_path, info("ProPlus2019Volume"), dl_exc=download.DownloadError("cancelled", "x"))
    assert h2.run().kind == "cancelled"


def test_flow_unexpected_exception_does_not_crash(tmp_path):
    h = Harness(tmp_path, info("ProPlus2019Volume"), fetch_exc=ZeroDivisionError("boom"))
    out = h.run()
    assert out.kind == "error" and "журнал" in out.message
    assert "ZeroDivisionError" in (tmp_path / "flow.log").read_text(encoding="utf-8")


def test_flow_unsupported_platform(tmp_path):
    h = Harness(tmp_path, info("ProPlus2021Volume"))
    h.flow.supported = False
    assert h.run().kind == "unsupported" and h.calls == []
