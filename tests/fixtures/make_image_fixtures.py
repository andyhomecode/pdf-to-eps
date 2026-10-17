#!/usr/bin/env python3
# Rebuild the image-only test PDFs:
#   python3 tests/fixtures/make_image_fixtures.py
#
# photo.pdf: smooth shading, which the filter should dither (Atkinson)
# qr.pdf:    black and white blocks, which the filter should threshold

import math
import os
import random

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def photo() -> Image.Image:
    w, h = 400, 300
    img = Image.new("L", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            # A lit sphere on a horizontal gradient
            d = math.hypot(x - 200, y - 150) / 120
            v = 60 + 150 * x / w if d > 1 else 255 * (1 - 0.8 * d * d)
            px[x, y] = max(0, min(255, int(v)))
    return img


def qr() -> Image.Image:
    rng = random.Random(42)
    cells, cell = 25, 8
    img = Image.new("L", (cells * cell, cells * cell), 255)
    px = img.load()
    for cy in range(cells):
        for cx in range(cells):
            if rng.random() < 0.5:
                for y in range(cy * cell, (cy + 1) * cell):
                    for x in range(cx * cell, (cx + 1) * cell):
                        px[x, y] = 0
    return img


if __name__ == "__main__":
    # Pillow writes a one-page PDF with the image at this resolution
    photo().save(os.path.join(HERE, "photo.pdf"), resolution=100)
    qr().save(os.path.join(HERE, "qr.pdf"), resolution=100)
