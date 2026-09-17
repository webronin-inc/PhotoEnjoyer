"""Версия приложения и утилиты сравнения."""
__version__ = "5.0.19"
__release_date__ = "2026-09-17"


def parse(v: str):
    """'5.0.1-beta' -> (5, 0, 1)"""
    v = (v or "0").strip()
    main = v.split("-")[0].split("+")[0]
    nums = []
    for part in main.split("."):
        try:
            nums.append(int(part))
        except ValueError:
            nums.append(0)
    return tuple(nums) or (0,)


def compare(a: str, b: str) -> int:
    """-1 если a<b, 0 если равны, 1 если a>b."""
    pa, pb = parse(a), parse(b)
    n = max(len(pa), len(pb))
    pa += (0,) * (n - len(pa))
    pb += (0,) * (n - len(pb))
    return (pa > pb) - (pa < pb)


def is_newer(candidate: str, current: str = None) -> bool:
    current = current or __version__
    return compare(candidate, current) > 0
