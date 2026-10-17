#!/usr/bin/env python3
# Rebuild the image test fixtures:
#   python3 tests/fixtures/make_image_fixtures.py
#
# photo.pdf: smooth shading, which the filter should dither (Atkinson)
# qr.pdf:    black and white blocks, which the filter should threshold
# rotated.jpg: photo.pdf's image stored sideways with EXIF orientation 6,
#              as phones do; it should print upright (wider than tall)
# logo.png:  QR blocks on a transparent background
# email.pdf: text with embedded images, like an email printed from a phone:
#            a full-width photo and a smaller QR code that should print,
#            a 1pt tracking pixel and a banner behind text that should not

import math
import os
import random
import subprocess

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


def ps_image(img: Image.Image, x: float, y: float, w: float, h: float) -> str:
    """PostScript to draw a grayscale image at x,y (bottom left), w x h points."""
    data = img.tobytes().hex()
    return (f"gsave {x} {y} translate {w} {h} scale\n"
            f"{img.width} {img.height} 8 [{img.width} 0 0 -{img.height} 0 {img.height}]\n"
            f"<{data}> image grestore\n")


def email_ps() -> str:
    banner = Image.new("L", (40, 6), 200)
    pixel = Image.new("L", (1, 1), 0)
    return "".join([
        "%!PS\n",
        "/Helvetica-Bold findfont 18 scalefont setfont 72 780 moveto (Your Ticket) show\n",
        "/Helvetica findfont 11 scalefont setfont\n",
        "72 760 moveto (Thanks for your order. Show the code below at the door to) show\n",
        "72 746 moveto (collect your badge. We can't wait to see you there.) show\n",
        ps_image(photo(), 72, 480, 451, 250),
        ps_image(qr(), 222, 300, 150, 150),
        ps_image(pixel, 300, 280, 1, 1),
        ps_image(banner, 72, 200, 451, 60),
        "/Helvetica-Bold findfont 14 scalefont setfont 90 225 moveto (Text over a banner image) show\n",
        "/Helvetica findfont 11 scalefont setfont 72 170 moveto (See you soon!) show\n",
        "showpage\n",
    ])


if __name__ == "__main__":
    # Pillow writes a one-page PDF with the image at this resolution
    photo().save(os.path.join(HERE, "photo.pdf"), resolution=100)
    qr().save(os.path.join(HERE, "qr.pdf"), resolution=100)

    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees clockwise to display
    photo().transpose(Image.Transpose.ROTATE_90).save(os.path.join(HERE, "rotated.jpg"), quality=85, exif=exif)

    logo = qr().convert("LA")
    logo.putalpha(qr().point(lambda v: 255 - v))  # white blocks transparent
    logo.save(os.path.join(HERE, "logo.png"))

    ps = os.path.join(HERE, "email.ps")
    with open(ps, "w") as f:
        f.write(email_ps())
    subprocess.run(["ps2pdf", "-sPAPERSIZE=a4", ps, os.path.join(HERE, "email.pdf")], check=True)
    os.unlink(ps)
