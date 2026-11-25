"""Статическая защита от затирания внутренних атрибутов Tkinter.

В 0.0.0.14–0.0.0.18 вкладки редактора делали `self._w = 330`, и редактор фото не
открывался («invalid command name "330"»). Имена ниже принадлежат Tk — присваивать
их в своих виджетах нельзя."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "photogrid"
FORBIDDEN = {"_w", "master", "tk", "children", "widgetName", "_name", "_tclCommands",
             "_last_child_ids"}


def _tk_subclasses(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for b in node.bases:
                txt = ast.unparse(b)
                if re.match(r"^(tk|ttk|tkinter)\.", txt) or txt in {
                        "Canvas", "Frame", "Label", "Toplevel", "Entry", "Button", "Tk"}:
                    yield node
                    break


def test_widgets_never_assign_tk_internal_names():
    bad = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in _tk_subclasses(tree):
            for n in ast.walk(cls):
                targets = []
                if isinstance(n, ast.Assign):
                    targets = n.targets
                elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
                    targets = [n.target]
                for t in targets:
                    if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                            and t.value.id == "self" and t.attr in FORBIDDEN):
                        bad.append(f"{path.relative_to(ROOT)}:{n.lineno} {cls.name}.{t.attr}")
    assert not bad, "затираются внутренние атрибуты Tk: " + ", ".join(bad)
