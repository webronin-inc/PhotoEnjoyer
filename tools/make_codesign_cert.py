"""Создаёт САМОПОДПИСАННЫЙ сертификат подписи кода.

    python tools/make_codesign_cert.py --out secrets/ --name "PhotoEnjoyer" --years 5

Результат:
    photoenjoyer-codesign.pfx   — ПРИВАТНЫЙ ключ + сертификат (под паролем). Храните в секрете:
                                  в репозиторий НЕ класть. Нужен только сборке.
    photoenjoyer-codesign.cer   — публичная часть. Её можно раздавать тем, кто хочет
                                  доверять вашим сборкам (см. tools/trust_certificate.ps1).
    pfx_base64.txt              — тот же PFX в base64 — для секрета GitHub
                                  CODESIGN_PFX_BASE64.

ВАЖНО: самоподписанный сертификат не доверен Windows по умолчанию. Предупреждение
SmartScreen он не убирает — подробности в docs/SIGNING.md.
"""
import argparse
import base64
import datetime
import getpass
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def make_certificate(common_name, org, years=5, key_size=3072):
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(subject).issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=365 * years))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]),
                           critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                           critical=False)
            .sign(key, hashes.SHA256()))
    return key, cert


def to_pfx(key, cert, password, name="PhotoEnjoyer"):
    """PFX, который понимают и старые Windows (3DES/SHA-1 для обёртки PKCS#12)."""
    try:
        enc = (serialization.PrivateFormat.PKCS12.encryption_builder()
               .kdf_rounds(50000)
               .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
               .hmac_hash(hashes.SHA1()).build(password.encode()))
    except Exception:
        enc = serialization.BestAvailableEncryption(password.encode())
    return pkcs12.serialize_key_and_certificates(name.encode(), key, cert, None, enc)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="secrets", help="куда сохранить файлы")
    ap.add_argument("--name", default="PhotoEnjoyer", help="имя издателя в сертификате")
    ap.add_argument("--org", default=None)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--password", default=os.environ.get("PE_SIGN_PASSWORD"))
    args = ap.parse_args(argv)
    pw = args.password or getpass.getpass("Пароль для PFX (запомните его): ")
    if len(pw) < 8:
        sys.exit("Пароль слишком короткий (от 8 символов)")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    key, cert = make_certificate(args.name, args.org or args.name, args.years)
    pfx = to_pfx(key, cert, pw, args.name)
    (out / "photoenjoyer-codesign.pfx").write_bytes(pfx)
    (out / "photoenjoyer-codesign.cer").write_bytes(cert.public_bytes(serialization.Encoding.DER))
    (out / "pfx_base64.txt").write_text(base64.b64encode(pfx).decode("ascii"), encoding="ascii")
    fp = cert.fingerprint(hashes.SHA256()).hex().upper()
    print("Готово:", out.resolve())
    print("Отпечаток SHA-256:", fp)
    print("\nДальше:\n 1) НЕ коммитьте папку", out, "(добавьте в .gitignore)\n"
          " 2) В GitHub: Settings → Secrets → Actions → CODESIGN_PFX_BASE64 = содержимое "
          "pfx_base64.txt, CODESIGN_PASSWORD = ваш пароль\n"
          " 3) .cer раздавайте тем, кто захочет доверять вашим сборкам")


if __name__ == "__main__":
    main()
