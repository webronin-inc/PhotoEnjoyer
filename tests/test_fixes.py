"""Регрессионные тесты на исправленные баги. Запуск: pytest -q"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))


# ------------------------------------------------------------------ version
def test_version_parse_accepts_v_prefix():
    from photogrid.version import parse, is_newer
    assert parse("v5.0.2") == (5, 0, 2)
    assert parse("V1.2") == (1, 2)
    assert is_newer("v0.0.0.10", "0.0.0.9") is True


# ------------------------------------------------------------------- config
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_config_restores_plugin_settings(monkeypatch, tmp_path):
    """watermark/updates сохранялись, но не загружались при старте."""
    _isolated_home(monkeypatch, tmp_path)
    from photogrid.config import Config

    c = Config()
    c.data["watermark"] = {"enabled": True, "text": "hello"}
    c.data["updates"] = {"auto_check": False}
    c["cell_size"] = 1234
    c.save()

    c2 = Config()
    assert c2.data["watermark"] == {"enabled": True, "text": "hello"}
    assert c2.data["updates"] == {"auto_check": False}
    assert c2["cell_size"] == 1234


def test_config_rejects_garbage(monkeypatch, tmp_path):
    _isolated_home(monkeypatch, tmp_path)
    from photogrid.config import Config, DEFAULTS

    c = Config()
    c.path.write_text('{"layout": "нет такой", "mode": "zzz", '
                      '"cell_size": "big", "theme": 5}', encoding="utf-8")
    c2 = Config()
    assert c2["layout"] == DEFAULTS["layout"]
    assert c2["mode"] == DEFAULTS["mode"]
    assert c2["cell_size"] == DEFAULTS["cell_size"]
    assert c2["theme"] == DEFAULTS["theme"]

    c.path.write_text("не json", encoding="utf-8")
    assert Config()["cell_size"] == DEFAULTS["cell_size"]


def test_layout_cells():
    from photogrid.config import layout_cells
    assert layout_cells("1×1 — одно фото") == 1
    assert layout_cells("3×3 — сетка") == 9
    assert layout_cells("неизвестная") == 4


# --------------------------------------------------------------------- core
def test_load_rgb_applies_exif_orientation(tmp_path):
    """Фото с EXIF-поворотом не должны ложиться «на бок»."""
    from PIL import Image
    from photogrid.core import load_rgb

    img = Image.new("RGB", (200, 100), "#ff0000")
    exif = Image.Exif()
    exif[0x0112] = 6            # повернуть на 90° по часовой
    p = tmp_path / "rot.jpg"
    img.save(p, exif=exif)

    out = load_rgb(str(p), "#ffffff")
    assert out.size == (100, 200)


def test_load_rgb_transparency_uses_background(tmp_path):
    from PIL import Image
    from photogrid.core import load_rgb

    p = tmp_path / "t.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(p)
    assert load_rgb(str(p), "#00ff00").getpixel((5, 5)) == (0, 255, 0)


def test_load_rgb_releases_file(tmp_path):
    """На Windows открытый файл нельзя удалить — load_rgb должен его закрывать."""
    from PIL import Image
    from photogrid.core import load_rgb

    p = tmp_path / "a.png"
    Image.new("RGB", (10, 10), "#123456").save(p)
    load_rgb(str(p), "#ffffff")
    p.unlink()
    assert not p.exists()


def test_collage_single_cell_and_unknown_layout(tmp_path):
    from PIL import Image
    from photogrid.core import build_collage
    from photogrid.config import DEFAULTS

    p = tmp_path / "a.png"
    Image.new("RGB", (50, 50), "#ff0000").save(p)
    cfg = dict(DEFAULTS, layout="1×1 — одно фото", cell_size=100, border=0)
    assert build_collage([str(p)], cfg).size == (100, 100)

    cfg["layout"] = "несуществующая"       # раньше — KeyError
    assert build_collage([str(p)], cfg).size == (200, 200)


# ------------------------------------------------------------------ updater
class _FakeRoot:
    """Как настоящий Tk: after() кладёт вызов в очередь главного потока,
    он выполняется ПОЗЖЕ — когда рабочий поток уже вышел из блока except."""
    def __init__(self):
        self.queue = []

    def after(self, _ms, fn):
        self.queue.append(fn)

    def run_pending(self, timeout=5):
        import time
        deadline = time.time() + timeout
        while not self.queue and time.time() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)                      # дать потоку завершиться
        while self.queue:
            self.queue.pop(0)()


def test_check_async_reports_errors(monkeypatch):
    """`except ... as e` + lambda давало NameError: ошибка проверки терялась."""
    from photogrid import updater

    def boom(*a, **k):
        raise ValueError("нет сети")
    monkeypatch.setattr(updater, "fetch_manifest", boom)

    got, root = [], _FakeRoot()
    updater.check_async(root, "https://x", lambda i, e: got.append((i, e)))
    root.run_pending()
    assert got, "callback не был вызван"
    info, err = got[0]
    assert info is None
    assert isinstance(err, ValueError) and "нет сети" in str(err)


def test_check_async_success(monkeypatch):
    from photogrid import updater

    monkeypatch.setattr(updater, "fetch_manifest",
                        lambda *a, **k: {"version": "99.0.0"})
    got, root = [], _FakeRoot()
    updater.check_async(root, "https://x", lambda i, e: got.append((i, e)))
    root.run_pending()
    info, err = got[0]
    assert err is None and info["available"] is True


class _FakeResponse:
    def __init__(self, chunks, length):
        self._chunks = list(chunks)
        self.headers = {"Content-Length": str(length)}

    def read(self, _n):
        if not self._chunks:
            return b""
        c = self._chunks.pop(0)
        if isinstance(c, Exception):
            raise c
        return c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_is_atomic(monkeypatch, tmp_path):
    from photogrid import updater

    dest = tmp_path / "plugin.py"
    dest.write_text("OLD", encoding="utf-8")

    # обрыв посреди загрузки
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse([b"abc", OSError("reset")], 6))
    with pytest.raises(OSError):
        updater.download_file("https://x", dest)
    assert dest.read_text(encoding="utf-8") == "OLD"       # старый файл цел
    assert not list(tmp_path.glob("*.part"))               # мусора нет

    # сервер отдал меньше, чем обещал в Content-Length
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse([b"abc"], 10))
    with pytest.raises(IOError):
        updater.download_file("https://x", dest)
    assert dest.read_text(encoding="utf-8") == "OLD"

    # успех
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse([b"NEW"], 3))
    updater.download_file("https://x", dest)
    assert dest.read_text(encoding="utf-8") == "NEW"


def test_plugin_update_sanitizes_name_and_keeps_old_on_bad_sha(monkeypatch,
                                                               tmp_path):
    from photogrid import updater

    monkeypatch.setattr(updater, "external_plugins_dir", lambda: tmp_path)

    def fake_download(url, dest, progress_cb=None, chunk=0):
        Path(dest).write_text("NEW", encoding="utf-8")
        return dest
    monkeypatch.setattr(updater, "download_file", fake_download)

    # попытка выйти за пределы папки плагинов
    rep = updater.apply_plugin_updates(
        [{"name": "../../evil", "url": "https://x"}])
    assert rep[0]["ok"] and rep[0]["name"] == "evil.py"
    assert (tmp_path / "evil.py").exists()
    assert not (tmp_path.parent / "evil.py").exists()

    # неверный sha256 не должен стирать рабочий плагин
    (tmp_path / "good.py").write_text("WORKING", encoding="utf-8")
    rep = updater.apply_plugin_updates(
        [{"name": "good", "url": "https://x", "sha256": "0" * 64}])
    assert not rep[0]["ok"]
    assert (tmp_path / "good.py").read_text(encoding="utf-8") == "WORKING"
    assert not list(tmp_path.glob("*.new"))


def test_updater_unsubscribe():
    from photogrid import updater

    calls = []
    fn = calls.append
    updater.subscribe(fn)
    n = len(calls)
    updater.unsubscribe(fn)
    updater.set_pending(None)
    assert len(calls) == n


# -------------------------------------------------- UI-зависимые (нужен tkinter)
def test_batch_collect_jobs(tmp_path):
    pytest.importorskip("tkinter")
    from PIL import Image
    from photogrid.screens import batch

    class Var:
        def __init__(self, v):
            self.v = v

        def get(self):
            return self.v

    def make(folder, n):
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            Image.new("RGB", (4, 4)).save(folder / f"{i}.png")

    make(tmp_path / "a" / "same", 4)
    make(tmp_path / "b" / "same", 4)         # то же имя папки, другой родитель
    make(tmp_path / "out", 4)                # папка результата внутри входной
    make(tmp_path / "few", 2)

    logs = []
    jobs = batch._collect_jobs({"recursive": Var(True)}, str(tmp_path),
                               str(tmp_path / "out"), 4, logs.append)
    names = [n for n, _ in jobs]
    assert len(names) == 2 and len(set(names)) == 2      # без коллизий имён
    assert all(len(photos) == 4 for _, photos in jobs)
    assert not any("out" in n for n in names)            # результат не обходится

    # раскладка на 1 фото → задание на каждое фото
    jobs = batch._collect_jobs({"recursive": Var(False)}, str(tmp_path / "few"),
                               str(tmp_path / "x"), 1, logs.append)
    assert len(jobs) == 2
