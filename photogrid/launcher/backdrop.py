"""Неоновый фон окон-«витрин»: градиент, плавающие светящиеся пятна, искры."""
import math
import random
import tkinter as tk

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from .. import anim, icons
from ..ui_widgets import _blend_hex


class NeonBackdrop:
    def __init__(self, canvas, width, height, palette):
        self.cv, self.w, self.h, self.p = canvas, width, height, palette
        self._phase = 0.0
        self._job = None
        self._closed = False
        bg = Image.new("RGB", (width, height))
        d = ImageDraw.Draw(bg)
        for y in range(height):
            t = y / height
            d.line([(0, y), (width, y)], fill=(int(9 + 9 * t), int(9 + 6 * t), int(22 + 22 * t)))
        self._bg = ImageTk.PhotoImage(bg)
        canvas.create_image(0, 0, image=self._bg, anchor="nw", tags="backdrop")
        self.blobs = []
        for i, hue in enumerate(("violet", "cyan", "pink")):
            size = 420
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            col = tuple(int(icons.NEON[hue].lstrip("#")[j:j + 2], 16) for j in (0, 2, 4))
            ImageDraw.Draw(img).ellipse((70, 70, size - 70, size - 70), fill=col + (105,))
            ph = ImageTk.PhotoImage(img.filter(ImageFilter.GaussianBlur(62)))
            item = canvas.create_image(width * (0.2 + 0.3 * i), height * 0.5, image=ph, tags="backdrop")
            self.blobs.append([ph, item, random.uniform(0, 6.28), 0.55 + i * 0.22])
        self.parts = [[random.uniform(0, width), random.uniform(0, height), random.uniform(0.15, 0.5),
                       random.uniform(1.1, 2.4),
                       canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline="", tags="backdrop")]
                      for _ in range(34)]

    def start(self):
        if self._job is None and not self._closed:
            self._job = self.cv.after(40, self._tick)

    def stop(self):
        self._closed = True
        if self._job is not None:
            try:
                self.cv.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self):
        self._job = None
        if self._closed:
            return
        try:
            if self.cv.winfo_exists() and anim.effects_enabled():
                self._phase += 0.012
                for ph, item, off, speed in self.blobs:
                    t = self._phase * speed + off
                    self.cv.coords(item, self.w / 2 + math.sin(t) * self.w * 0.34,
                                   self.h / 2 + math.cos(t * 0.8) * self.h * 0.30)
                for pt in self.parts:
                    pt[1] -= pt[2]
                    if pt[1] < -4:
                        pt[0], pt[1] = random.uniform(0, self.w), self.h + 4
                    r = pt[3]
                    self.cv.coords(pt[4], pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r)
                    self.cv.itemconfigure(pt[4], fill=_blend_hex(
                        "#ffffff", self.p["bg"], 0.30 + 0.22 * math.sin(pt[1] / 40)))
            self._job = self.cv.after(40, self._tick)
        except tk.TclError:
            pass
