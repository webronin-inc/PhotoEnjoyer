"""Сессия редактирования фото без привязки к Tk.

Держит состояние (EditState), историю отмен/повторов, кэш рендера и
логику инструментов мыши (кисть, фигуры, области, перемещение кадра).
Интерфейс (plugins/photo_editor.py) только передаёт сюда координаты и
показывает картинку — поэтому вся логика проверяется тестами без окна.
"""
import copy

from . import editor_core as ec

# размеры мазка/текста задаются слайдером 1..40 и переводятся в долю длинной стороны
BRUSH_UNIT = 0.0015
TEXT_UNIT = 0.004

SHAPE_TOOLS = ("line", "arrow", "rect", "ellipse")
FREEHAND_TOOLS = ("brush", "eraser")
MIN_SHAPE = 0.004          # короче этого фигуру не создаём (случайный клик)
MIN_POINT_STEP = 0.0015    # прореживание точек кисти


def _clamp01(v):
    return max(0.0, min(1.0, float(v)))


class EditorSession:
    HISTORY_LIMIT = 100

    def __init__(self, full_img, bg="#ffffff", preview_side=1000):
        self.full = full_img.convert("RGB")
        self.bg = bg
        self.base = ec.make_preview_base(self.full, preview_side)
        self.state = ec.EditState()
        self._undo = []
        self._redo = []
        self._stage = None            # кэш: результат без рисования
        self._stage_key = None
        self._temp_ops = []           # то, что рисуется прямо сейчас
        self._gesture = None
        self._last_snapshot_key = None

    # ------------------------------------------------------------ история
    def _snapshot(self):
        return {"v": dict(self.state.v), "ops": list(self.state.ops)}

    @staticmethod
    def _snap_key(snap):
        return (tuple(sorted(snap["v"].items())),
                tuple(id(o) for o in snap["ops"]))

    def checkpoint(self):
        """Запоминает текущее состояние ПЕРЕД изменением (для Ctrl+Z)."""
        snap = self._snapshot()
        if self._undo and self._snap_key(self._undo[-1]) == self._snap_key(snap):
            return False
        self._undo.append(snap)
        if len(self._undo) > self.HISTORY_LIMIT:
            self._undo.pop(0)
        self._redo.clear()
        return True

    def _restore(self, snap):
        self.state.v = dict(snap["v"])
        self.state.ops = list(snap["ops"])
        self._temp_ops = []
        self._gesture = None

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    @property
    def changed(self):
        return not self.state.is_default

    def reset_all(self):
        if self.state.is_default:
            return
        self.checkpoint()
        self.state.reset_all()
        self._temp_ops = []

    def reset_frame(self):
        self.checkpoint()
        self.state.reset_frame()

    def reset_color(self):
        self.checkpoint()
        self.state.reset_color()

    # ----------------------------------------------------------- значения
    def set_value(self, key, value):
        self.state.set(key, value)

    def rotate90(self, steps=1):
        self.checkpoint()
        self.state.rotate90(steps)

    def flip(self, horizontal=True):
        self.checkpoint()
        self.state.flip(horizontal)

    def zoom_by(self, factor, checkpoint=True):
        if checkpoint:
            self.checkpoint()
        self.state.zoom_by(factor)

    def set_filter(self, name):
        if name not in ec.FILTERS:
            return
        self.checkpoint()
        self.state.set("filter", name)

    def auto_enhance(self):
        self.checkpoint()
        ec.auto_enhance(self.state)

    # -------------------------------------------------------------- рендер
    def _stage_cache_key(self):
        st = self.state
        return (tuple(sorted(st.v.items())),
                tuple(id(o) for o in st.ops if o.get("t") in ec.AREA_TOOLS))

    def render_view(self, compare=False):
        """Картинка для показа. compare=True — исходник без правок."""
        if compare:
            return self.base
        key = self._stage_cache_key()
        if key != self._stage_key or self._stage is None:
            self._stage = ec.render_base(self.base, self.state, self.bg)
            self._stage_key = key
        return ec.compose_paint(self._stage, self.state, self._temp_ops)

    def render_full(self):
        """Итог в полном разрешении (тяжёлый — вызывать в потоке)."""
        st = copy.deepcopy(self.state)
        return ec.render(self.full, st, self.bg)

    def filter_previews(self, side=84):
        """Миниатюры всех фильтров для вкладки «Фильтры»."""
        thumb = ec.make_preview_base(self.base, side * 2)
        thumb.thumbnail((side, side))
        out = {}
        for name in ec.FILTERS:
            out[name] = ec.apply_filter(thumb, name)
        return out

    # -------------------------------------------------------- рамка (pan)
    def pan_by(self, dx_norm, dy_norm):
        px, py = ec.pan_after_drag(self.state.v, dx_norm, dy_norm)
        self.state.v["pan_x"], self.state.v["pan_y"] = px, py

    # --------------------------------------------------- жесты рисования
    @property
    def drawing(self):
        return self._gesture is not None

    def pointer_down(self, tool, x, y, style=None):
        """Начало жеста. style: color, size (1..40), alpha (0..1), fill."""
        style = style or {}
        x, y = _clamp01(x), _clamp01(y)
        size = float(style.get("size", 10)) * BRUSH_UNIT
        base = {"color": style.get("color", "#ff3b30"), "size": size,
                "alpha": float(style.get("alpha", 1.0))}
        g = {"tool": tool, "start": (x, y)}

        if tool in FREEHAND_TOOLS:
            op = dict(base, t=tool, pts=[(x, y)])
            if tool == "eraser":
                op = {"t": "eraser", "pts": [(x, y)], "size": size * 1.6}
            g["op"] = op
            self._temp_ops = [op]
        elif tool in SHAPE_TOOLS:
            op = dict(base, t=tool, p0=(x, y), p1=(x, y),
                      fill=bool(style.get("fill", False)))
            g["op"] = op
            self._temp_ops = [op]
        elif tool in ec.AREA_TOOLS:
            g["op"] = {"t": tool, "rect": (x, y, x, y)}
            self._temp_ops = []
        elif tool == "pan":
            g["last"] = (x, y)
            self.checkpoint()
        else:
            return False
        self._gesture = g
        return True

    def pointer_move(self, x, y):
        """Возвращает True, если нужно перерисовать."""
        g = self._gesture
        if not g:
            return False
        x, y = _clamp01(x), _clamp01(y)
        tool, op = g["tool"], g.get("op")
        if tool in FREEHAND_TOOLS:
            last = op["pts"][-1]
            if abs(x - last[0]) + abs(y - last[1]) < MIN_POINT_STEP:
                return False
            op["pts"].append((x, y))
        elif tool in SHAPE_TOOLS:
            op["p1"] = (x, y)
        elif tool in ec.AREA_TOOLS:
            x0, y0 = g["start"]
            op["rect"] = (min(x0, x), min(y0, y), max(x0, x), max(y0, y))
            return False            # область показывает рамка в UI, рендер не нужен
        elif tool == "pan":
            lx, ly = g["last"]
            self.pan_by(x - lx, y - ly)
            g["last"] = (x, y)
        return True

    def area_rect(self):
        """Текущая рамка выделения (для резиновой рамки в UI) или None."""
        g = self._gesture
        if g and g["tool"] in ec.AREA_TOOLS:
            return g["op"]["rect"]
        return None

    def pointer_up(self, x=None, y=None):
        """Завершает жест. Возвращает True, если состояние изменилось."""
        g = self._gesture
        if not g:
            return False
        if x is not None:
            self.pointer_move(x, y)
        self._gesture = None
        tool, op = g["tool"], g.get("op")
        self._temp_ops = []

        if tool == "pan":
            return True
        if tool in FREEHAND_TOOLS:
            self.checkpoint()
            self.state.add_op(op)
            return True
        if tool in SHAPE_TOOLS:
            (x0, y0), (x1, y1) = op["p0"], op["p1"]
            if abs(x1 - x0) + abs(y1 - y0) < MIN_SHAPE:
                return False
            self.checkpoint()
            self.state.add_op(op)
            return True
        if tool in ec.AREA_TOOLS:
            x0, y0, x1, y1 = op["rect"]
            if (x1 - x0) < MIN_SHAPE or (y1 - y0) < MIN_SHAPE:
                return False
            self.checkpoint()
            self.state.add_op(op)
            return True
        return False

    def add_text(self, x, y, text, style=None):
        style = style or {}
        text = (text or "").strip("\n")
        if not text.strip():
            return False
        self.checkpoint()
        self.state.add_op({
            "t": "text", "pos": (_clamp01(x), _clamp01(y)), "text": text,
            "color": style.get("color", "#ffffff"),
            "size": float(style.get("size", 12)) * TEXT_UNIT,
            "alpha": float(style.get("alpha", 1.0)),
        })
        return True

    def clear_drawing(self):
        if not self.state.ops:
            return False
        self.checkpoint()
        self.state.ops.clear()
        return True
