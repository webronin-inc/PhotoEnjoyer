"""Описание установщика Word, которое выдаёт сервер (подписано его ключом)."""
import re
from dataclasses import dataclass, field

from ..account.api import ApiError, NetworkError
from ..account.tokens import verify_token

FILE_RE = re.compile(r"^[A-Za-z0-9._\- ]{1,80}\.(exe|msi)$", re.I)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class PackageError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Package:
    url: str
    sha256: str
    filename: str
    target: str = "Word 2021"
    match: tuple = ("2021",)
    size: int = 0
    args: list = field(default_factory=list)
    config_xml: str = ""
    notes: str = ""

    @property
    def host(self):
        m = re.match(r"^https?://([^/:]+)", self.url)
        return m.group(1) if m else ""

    def size_text(self):
        if not self.size:
            return "размер неизвестен"
        gb = self.size / 1024 ** 3
        return f"{gb:.1f} ГБ" if gb >= 1 else f"{max(1, round(self.size / 1024 ** 2))} МБ"


def _safe_url(url):
    if url.startswith("https://") and len(url) > 12 and not re.search(r"[\s\"'<>]", url):
        return True
    return bool(re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/[^\s\"'<>]*$", url))


def parse_manifest(token, pub, now=None):
    """Проверяет подпись и содержимое. Любое отклонение → PackageError."""
    claims = verify_token(pub, token, now=now)
    if not claims or claims.get("kind") != "word" or not isinstance(claims.get("pkg"), dict):
        raise PackageError("bad_manifest", "Описание установщика не прошло проверку подлинности "
                           "— установка отменена.")
    b = claims["pkg"]
    url, sha, fname = str(b.get("url", "")), str(b.get("sha256", "")).lower(), str(b.get("filename", ""))
    if not b.get("enabled") or not _safe_url(url) or not SHA_RE.match(sha) or not FILE_RE.match(fname):
        raise PackageError("bad_manifest", "Описание установщика на сервере заполнено неверно. "
                           "Сообщите администратору.")
    match = tuple(str(m) for m in b.get("match", ["2021"]) if str(m).strip()) or ("2021",)
    return Package(url=url, sha256=sha, filename=fname, target=str(b.get("target", "Word 2021")),
                   match=match, size=int(b.get("size", 0) or 0),
                   args=[str(a) for a in b.get("args", [])][:20],
                   config_xml=str(b.get("config_xml", "")), notes=str(b.get("notes", "")))


def fetch_package(api, pub, now=None):
    try:
        resp = api.software_word()
    except NetworkError:
        raise PackageError("network", "Нет связи с сервером. Проверьте интернет и повторите.")
    except ApiError as e:
        if e.code == "not_configured":
            raise PackageError("not_configured", "Установщик Word ещё не загружен на сервер. "
                               "Обратитесь к администратору.")
        if e.code.startswith("license_"):
            raise PackageError("license", "Для установки нужна активная лицензия.")
        raise PackageError(e.code, e.message)
    return parse_manifest(resp.get("manifest", ""), pub, now)
