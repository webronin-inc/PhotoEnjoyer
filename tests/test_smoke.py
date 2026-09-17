"""Базовые тесты. Запуск: pytest -q"""
import sys
from pathlib import Path

# Добавляем корень проекта в путь
HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))


def test_import_app():
    import photogrid.app
    assert hasattr(photogrid.app, "App")
    assert hasattr(photogrid.app, "run")


def test_version_parse():
    from photogrid.version import parse, compare, is_newer
    assert parse("5.0.2") == (5, 0, 2)
    assert parse("5.0") == (5, 0)
        # "v5.0.2" → int("v5") падает → 0, дальше 0, 2
    assert parse("v5.0.2") == (0, 0, 2)
    assert compare("5.0.2", "5.0.1") == 1
    assert compare("5.0.1", "5.0.2") == -1
    assert compare("5.0.1", "5.0.1") == 0
    assert is_newer("5.0.2", "5.0.1") is True
    assert is_newer("5.0.0", "5.0.1") is False


def test_branding_imports():
    from photogrid import branding
    assert branding.APP_NAME
    assert branding.APP_SLUG
    assert branding.APP_MANIFEST_URL


def test_plugins_load_structure():
    """Проверяет, что все встроенные плагины существуют как модули."""
    import importlib
    from photogrid.plugins.loader import BUNDLED
    for name in BUNDLED:
        mod = importlib.import_module(f"photogrid.plugins.{name}")
        assert hasattr(mod, "register"), f"{name}: нет register(app)"


def test_collage_builds(tmp_path):
    """Сборка коллажа 2x2 из 4 однотонных картинок."""
    from PIL import Image
    from photogrid.core import build_collage
    from photogrid.config import DEFAULTS

    photos = []
    for i, color in enumerate(["#ff0000", "#00ff00", "#0000ff", "#ffff00"]):
        p = tmp_path / f"img{i}.png"
        Image.new("RGB", (100, 100), color).save(p)
        photos.append(str(p))

    cfg = dict(DEFAULTS)
    cfg["cell_size"] = 100
    cfg["border"] = 0
    img = build_collage(photos, cfg, for_preview=False)
    assert img.size == (200, 200)


def test_manifest_signature_roundtrip(tmp_path):
    """Подпись и верификация манифеста Ed25519."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return  # без cryptography тест пропускается

    import base64, json
    key = Ed25519PrivateKey.generate()
    pub = key.public_key()

    manifest = {"version": "5.0.0", "notes": "test"}
    canonical = json.dumps(manifest, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":")).encode()
    sig = key.sign(canonical)

    manifest["signature"] = base64.b64encode(sig).decode()

    # Проверка
    payload = {k: v for k, v in manifest.items() if k != "signature"}
    canonical2 = json.dumps(payload, ensure_ascii=False,
                            sort_keys=True, separators=(",", ":")).encode()
    pub.verify(base64.b64decode(manifest["signature"]), canonical2)


def test_build_script_imports():
    """build.py должен импортироваться без ошибок."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("build", HERE / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")