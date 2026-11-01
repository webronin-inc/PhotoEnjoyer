"""Подпись кода: сертификат, команда signtool, пропуск без настроек."""
import base64
import sys
from pathlib import Path

import pytest

pytest.importorskip("cryptography")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import codesign                                    # noqa: E402
import make_codesign_cert as mk                    # noqa: E402
from cryptography.hazmat.primitives.serialization import pkcs12   # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID             # noqa: E402


def test_certificate_is_a_valid_code_signing_cert(tmp_path):
    key, cert = mk.make_certificate("PhotoEnjoyer", "PhotoEnjoyer", years=3, key_size=2048)
    eku = cert.extensions.get_extension_for_class(
        __import__("cryptography.x509", fromlist=["x"]).ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.CODE_SIGNING in eku
    assert cert.subject == cert.issuer                        # самоподписанный
    ku = cert.extensions.get_extension_for_class(
        __import__("cryptography.x509", fromlist=["x"]).KeyUsage).value
    assert ku.digital_signature and not ku.key_cert_sign
    pfx = mk.to_pfx(key, cert, "пароль-12345")
    k2, c2, _ = pkcs12.load_key_and_certificates(pfx, "пароль-12345".encode())
    assert c2.serial_number == cert.serial_number and k2 is not None


def test_cli_writes_all_files(tmp_path):
    mk.main(["--out", str(tmp_path), "--password", "secret-pass-1", "--years", "1"])
    assert (tmp_path / "photoenjoyer-codesign.pfx").exists()
    assert (tmp_path / "photoenjoyer-codesign.cer").exists()
    raw = base64.b64decode((tmp_path / "pfx_base64.txt").read_text())
    assert raw == (tmp_path / "photoenjoyer-codesign.pfx").read_bytes()


def test_signing_is_skipped_without_env(tmp_path, capsys):
    f = tmp_path / "a.exe"; f.write_bytes(b"x")
    assert codesign.sign_files([f], env={}) is False
    assert "пропущена" in capsys.readouterr().out


def test_sign_command_and_secret_masking(tmp_path, monkeypatch, capsys):
    f = tmp_path / "a.exe"; f.write_bytes(b"x")
    pfx = tmp_path / "c.pfx"; pfx.write_bytes(b"pfx")
    monkeypatch.setattr(codesign, "find_signtool", lambda: "signtool.exe")
    calls = []

    class R:
        returncode = 0
    ok = codesign.sign_files([f], env={"PE_SIGN_PFX": str(pfx), "PE_SIGN_PASSWORD": "TOPSECRET"},
                             runner=lambda cmd: calls.append(cmd) or R())
    assert ok and calls
    cmd = calls[0]
    assert cmd[:3] == ["signtool.exe", "sign", "/fd"] and "SHA256" in cmd
    assert "/tr" in cmd and "TOPSECRET" in cmd and str(f) == cmd[-1]
    assert "TOPSECRET" not in capsys.readouterr().out          # пароль не печатается в лог


def test_base64_pfx_is_materialised_and_removed(tmp_path, monkeypatch):
    f = tmp_path / "a.exe"; f.write_bytes(b"x")
    monkeypatch.setattr(codesign, "find_signtool", lambda: "signtool.exe")
    seen = {}

    class R:
        returncode = 0

    def runner(cmd):
        pfx = Path(cmd[cmd.index("/f") + 1])
        seen["path"], seen["data"] = pfx, pfx.read_bytes()
        return R()
    env = {"PE_SIGN_PFX_BASE64": base64.b64encode(b"PFXDATA").decode(), "PE_SIGN_PASSWORD": "pw"}
    assert codesign.sign_files([f], env=env, runner=runner)
    assert seen["data"] == b"PFXDATA" and not seen["path"].exists()


def test_failed_signing_reports_false(tmp_path, monkeypatch):
    f = tmp_path / "a.exe"; f.write_bytes(b"x")
    monkeypatch.setattr(codesign, "find_signtool", lambda: "signtool.exe")

    class R:
        returncode = 1
    assert codesign.sign_files([f], env={"PE_SIGN_PFX": "x", "PE_SIGN_PASSWORD": "pw"},
                               runner=lambda c: R()) is False


def test_enabled_requires_both_pfx_and_password():
    assert not codesign.enabled({"PE_SIGN_PFX": "x"})
    assert not codesign.enabled({"PE_SIGN_PASSWORD": "x"})
    assert codesign.enabled({"PE_SIGN_PFX_BASE64": "x", "PE_SIGN_PASSWORD": "x"})
