"""Скачивание установщика: докачка, прогресс, проверка размера и SHA-256."""
import hashlib
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path

CHUNK = 256 * 1024


class DownloadError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def sha256_file(path, progress=None, cancel=None):
    h = hashlib.sha256()
    total = os.path.getsize(path)
    done = 0
    with open(path, "rb") as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise DownloadError("cancelled", "Проверка отменена")
            buf = f.read(1 << 20)
            if not buf:
                break
            h.update(buf)
            done += len(buf)
            if progress:
                progress("verify", done, total)
    return h.hexdigest()


def enough_space(directory, need):
    try:
        return shutil.disk_usage(directory).free >= int(need * 1.15) + 50 * 1024 * 1024
    except OSError:
        return True                      # не смогли узнать — не мешаем


def download(url, dest_dir, filename, sha256, size=0, progress=None, cancel=None,
             timeout=30, opener=urllib.request.urlopen):
    """Возвращает путь к проверенному файлу. progress(stage, done, total)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    part = dest_dir / (filename + ".part")

    if dest.exists():                    # уже скачан раньше и цел — не качаем заново
        if sha256_file(dest, progress, cancel) == sha256:
            return dest
        dest.unlink(missing_ok=True)

    offset = part.stat().st_size if part.exists() else 0
    if size and offset > size:
        part.unlink()
        offset = 0
    if size and not enough_space(dest_dir, size - offset):
        raise DownloadError("space", "Недостаточно места на диске для загрузки установщика.")

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "PhotoEnjoyer-Word/1")
    if offset:
        req.add_header("Range", f"bytes={offset}-")
    try:
        resp = opener(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416 and offset:     # файл уже докачан целиком — проверим ниже
            resp = None
        else:
            raise DownloadError("http", f"Сервер ответил ошибкой {e.code} при загрузке установщика.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise DownloadError("network", "Не удалось скачать установщик: нет связи с сервером.") from e

    if resp is not None:
        with resp:
            status = getattr(resp, "status", 200)
            if status == 200 and offset:         # сервер не умеет докачку — начинаем заново
                offset = 0
            length = int(resp.headers.get("Content-Length") or 0)
            total = size or (length + offset)
            mode = "ab" if offset else "wb"
            done = offset
            try:
                with open(part, mode) as f:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise DownloadError("cancelled", "Загрузка отменена")
                        buf = resp.read(CHUNK)
                        if not buf:
                            break
                        f.write(buf)
                        done += len(buf)
                        if progress:
                            progress("download", done, total)
            except DownloadError:
                raise
            except (TimeoutError, OSError) as e:
                raise DownloadError("network", "Связь прервалась во время загрузки. "
                                    "Повторите — загрузка продолжится с места остановки.") from e

    if size and part.stat().st_size != size:
        raise DownloadError("size", "Файл скачан не полностью. Повторите — загрузка продолжится.")
    got = sha256_file(part, progress, cancel)
    if got != sha256:
        part.unlink(missing_ok=True)
        raise DownloadError("sha", "Контрольная сумма скачанного файла не совпала с ожидаемой — "
                            "файл удалён, установка отменена.")
    part.replace(dest)
    return dest
