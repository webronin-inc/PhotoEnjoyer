"""Тесты логики UI-виджетов, не требующие окна (нужен только импорт tkinter)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
pytest.importorskip("tkinter")


def test_particles_spread_over_whole_bar():
    """Раньше частицы возрождались через ~1–2 с и кучковались у левого края."""
    import random
    from photogrid.ui_widgets import _Particle

    random.seed(1)
    w, h = 1200, 34
    ps = [_Particle(w, h) for _ in range(14)]
    for _ in range(3000):                       # ~2.5 минуты работы
        for p in ps:
            p.step(w, h)
    xs = sorted(p.x for p in ps)
    assert xs[-1] > w * 0.6, xs                 # дальняя частица далеко от левого края
    assert sum(1 for x in xs if x > w * 0.25) >= 7, xs   # не кучкуются слева
    assert all(h * 0.1 <= p.y <= h * 0.9 for p in ps)


def test_particles_respawn_only_after_leaving_right_edge():
    from photogrid.ui_widgets import _Particle

    p = _Particle(100, 34, spread=False)
    assert p.x < 0
    start_x = p.x
    for _ in range(20):
        p.step(100, 34)
        assert p.x >= start_x                   # не «возрождается» посреди панели


def test_blend_hex_bounds():
    from photogrid.ui_widgets import _blend_hex
    assert _blend_hex("#ffffff", "#000000", 0) == "#000000"
    assert _blend_hex("#ffffff", "#000000", 1) == "#ffffff"
    assert _blend_hex("#ffffff", "#000000", 7) == "#ffffff"   # alpha зажимается
