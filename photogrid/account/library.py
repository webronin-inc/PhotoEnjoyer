"""Установка пакетов шаблонов из библиотеки (без интерфейса — легко тестировать)."""
import hashlib
import io
import json
import re
import zipfile

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_LAYOUT = "2×2 — квадрат"


class PackError(Exception):
    pass


def parse_pack(data, expected_sha256=None):
    """Проверяет архив и возвращает (метаданные, список шаблонов). Бросает PackError."""
    if expected_sha256 and hashlib.sha256(data).hexdigest() != expected_sha256:
        raise PackError("Файл повреждён при скачивании (не совпала контрольная сумма)")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        if "pack.json" not in names or len(names) > 20:
            raise PackError("В пакете нет pack.json")
        if any(n.startswith("/") or ".." in n for n in names):
            raise PackError("Недопустимые пути в архиве")
        if sum(i.file_size for i in zf.infolist()) > 4 * 1024 * 1024:
            raise PackError("Пакет слишком большой")
        meta = json.loads(zf.read("pack.json").decode("utf-8"))
    except zipfile.BadZipFile:
        raise PackError("Это не пакет шаблонов")
    except (ValueError, KeyError):
        raise PackError("Не удалось прочитать pack.json")
    tpls = meta.get("templates") if isinstance(meta, dict) else None
    if not isinstance(tpls, list) or not tpls:
        raise PackError("В пакете нет шаблонов")
    return meta, tpls[:100]


def clean_template(t, layouts):
    """Приводит шаблон из пакета к безопасному виду (всё проверяем ещё раз —
    сервер мог быть скомпрометирован, а пакет — подменён)."""
    name = str(t.get("name", "")).strip()[:40]
    if not name:
        raise PackError("У шаблона нет имени")
    out = {"desc": str(t.get("desc", ""))[:80],
           "layout": t.get("layout") if t.get("layout") in layouts else DEFAULT_LAYOUT,
           "mode": t.get("mode") if t.get("mode") in ("fit", "fill") else "fit"}
    for key, lo, hi, default in (("cell_size", 100, 4000, 800), ("border", 0, 200, 10)):
        try:
            v = int(t.get(key, default))
        except (TypeError, ValueError):
            v = default
        out[key] = min(hi, max(lo, v))
    for key, default in (("border_color", "#ffffff"), ("bg_color", "#ffffff")):
        v = str(t.get(key, default))
        out[key] = v.lower() if COLOR_RE.match(v) else default
    return name, out


def install(data, expected_sha256, user_templates, layouts, pack_name=""):
    """Добавляет шаблоны пакета в словарь пользовательских шаблонов.

    Возвращает (сколько_добавлено, новый_словарь). Одноимённые шаблоны не затираются:
    к имени добавляется название пакета."""
    meta, tpls = parse_pack(data, expected_sha256)
    result = dict(user_templates)
    added = 0
    suffix = (pack_name or meta.get("name") or "пакет")[:20]
    for t in tpls:
        if not isinstance(t, dict):
            continue
        name, tpl = clean_template(t, layouts)
        if name in result and result[name] != tpl:
            name = f"{name} ({suffix})"[:60]
        tpl["pack"] = str(meta.get("id", ""))[:40]
        if result.get(name) != tpl:
            added += 1
        result[name] = tpl
    return added, result


def build_pack(pack_id, name, description, author, templates):
    """Собирает zip-пакет из словаря шаблонов (для администратора)."""
    items = []
    for n, t in templates.items():
        items.append({"name": n, **{k: v for k, v in t.items() if k != "pack"}})
    meta = {"id": pack_id, "name": name, "description": description, "author": author,
            "version": "1", "templates": items}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.json", json.dumps(meta, ensure_ascii=False, indent=1))
    return buf.getvalue()
