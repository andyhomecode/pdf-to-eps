#!/usr/bin/env python3
# escpos_preview — decode ESC/POS bytes into readable text, so filter output
# can be checked without printing.
#
# Usage:
#   python3 tools/escpos_preview.py output.escpos
#   python3 pdf2escpos.py 1 u t 1 "" doc.pdf | python3 tools/escpos_preview.py -
#   python3 tools/escpos_preview.py --png-dir /tmp/imgs output.escpos
#
# Text prints as-is. Commands print as tags, e.g. [INIT] [CENTER] [B]...[/B]
# [2H] [RED] [IMG 576x312] [CUT]. Unknown commands print as [?ESC x] etc.

import argparse
import os
import sys
from typing import List, Optional

ESC, GS, FS = 0x1B, 0x1D, 0x1C

ALIGN = {0: "[LEFT]", 1: "[CENTER]", 2: "[RIGHT]", 48: "[LEFT]", 49: "[CENTER]", 50: "[RIGHT]"}


class Decoder:
    def __init__(self, data: bytes, codepage: str, png_dir: Optional[str]):
        self.data = data
        self.i = 0
        self.codepage = codepage
        self.png_dir = png_dir
        self.out: List[str] = []
        self.text = bytearray()
        self.image_count = 0
        # Current style, so off-commands only print when something was on
        self.bold = False
        self.underline = False
        self.red = False
        self.align = "[LEFT]"

    # ---------- helpers ----------
    def take(self, n: int) -> bytes:
        chunk = self.data[self.i:self.i + n]
        if len(chunk) < n:
            raise EOFError
        self.i += n
        return chunk

    def byte(self) -> int:
        return self.take(1)[0]

    def flush_text(self) -> None:
        if self.text:
            self.out.append(self.text.decode(self.codepage, errors="replace"))
            self.text.clear()

    def tag(self, s: str) -> None:
        self.flush_text()
        self.out.append(s)

    def save_image(self, width: int, height: int, rows: List[bytes]) -> None:
        """rows: one bytes object per pixel row, 1 bit per pixel, MSB first, 1 = black."""
        self.image_count += 1
        name = ""
        if self.png_dir:
            try:
                from PIL import Image
                img = Image.new("1", (width, height), 1)
                px = img.load()
                for y, row in enumerate(rows):
                    for x in range(width):
                        if row[x >> 3] & (0x80 >> (x & 7)):
                            px[x, y] = 0
                os.makedirs(self.png_dir, exist_ok=True)
                path = os.path.join(self.png_dir, f"image{self.image_count:02d}.png")
                img.save(path)
                name = f" -> {path}"
            except ImportError:
                name = " (Pillow missing, not saved)"
        self.tag(f"[IMG {width}x{height}{name}]")

    # ---------- commands ----------
    def do_esc(self) -> None:
        c = self.byte()
        ch = chr(c)
        if ch == "@":
            self.bold = self.underline = self.red = False
            self.align = "[LEFT]"
            self.tag("[INIT]")
        elif ch == "M":
            self.tag(f"[FONT {'AB'[self.byte() & 1]}]")
        elif ch == "2":
            self.tag("[LINESPACE default]")
        elif ch == "3":
            self.tag(f"[LINESPACE {self.byte()}]")
        elif ch == "a":
            align = ALIGN.get(self.byte(), "[ALIGN ?]")
            if align != self.align:
                self.tag(align)
            self.align = align
        elif ch == "E":
            on = bool(self.byte() & 1)
            if on != self.bold:
                self.tag("[B]" if on else "[/B]")
            self.bold = on
        elif ch == "-":
            on = (self.byte() & 3) != 0
            if on != self.underline:
                self.tag("[U]" if on else "[/U]")
            self.underline = on
        elif ch == "!":
            n = self.byte()
            parts = []
            if n & 0x01: parts.append("fontB")
            if n & 0x08: parts.append("bold")
            if n & 0x10: parts.append("2H")
            if n & 0x20: parts.append("2W")
            if n & 0x80: parts.append("underline")
            self.tag(f"[MODE {' '.join(parts) or 'normal'}]")
        elif ch == "t":
            self.tag(f"[CODEPAGE {self.byte()}]")
        elif ch == "r":
            on = bool(self.byte() & 1)
            if on != self.red:
                self.tag("[RED]" if on else "[/RED]")
            self.red = on
        elif ch == "d":
            self.tag(f"[FEED {self.byte()}]")
        elif ch == "m":
            self.tag("[CUT partial ESC m]")
        elif ch == "i":
            self.tag("[CUT full ESC i]")
        elif ch == "*":
            # ESC * m nL nH d1...dk: bit image column format
            m = self.byte()
            nl, nh = self.byte(), self.byte()
            cols = nl + nh * 256
            bytes_per_col = 3 if m in (32, 33) else 1
            data = self.take(cols * bytes_per_col)
            height = bytes_per_col * 8
            # Convert column-major to row-major for saving
            row_bytes = (cols + 7) // 8
            rows = [bytearray(row_bytes) for _ in range(height)]
            for x in range(cols):
                for b in range(bytes_per_col):
                    v = data[x * bytes_per_col + b]
                    for bit in range(8):
                        if v & (0x80 >> bit):
                            y = b * 8 + bit
                            rows[y][x >> 3] |= 0x80 >> (x & 7)
            self.save_image(cols, height, [bytes(r) for r in rows])
        else:
            self.tag(f"[?ESC {ch!r}]")

    def do_gs(self) -> None:
        c = self.byte()
        ch = chr(c)
        if ch == "V":
            m = self.byte()
            if m in (65, 66):  # function B: feed n then cut
                n = self.byte()
                self.tag(f"[CUT {'full' if m == 65 else 'partial'} feed={n}]")
            else:
                self.tag(f"[CUT {'full' if m in (0, 48) else 'partial'}]")
        elif ch == "!":
            n = self.byte()
            w, h = (n >> 4) + 1, (n & 0x0F) + 1
            self.tag("[SIZE normal]" if (w, h) == (1, 1) else f"[SIZE {w}Wx{h}H]")
        elif ch == "v":
            # GS v 0 m xL xH yL yH d1...dk: raster bit image
            if self.byte() != 0x30:
                self.tag("[?GS v]")
                return
            self.byte()  # m (scaling), ignored
            xl, xh, yl, yh = self.take(4)
            row_bytes = xl + xh * 256
            height = yl + yh * 256
            data = self.take(row_bytes * height)
            rows = [data[y * row_bytes:(y + 1) * row_bytes] for y in range(height)]
            self.save_image(row_bytes * 8, height, rows)
        else:
            self.tag(f"[?GS {ch!r}]")

    def run(self) -> str:
        try:
            while self.i < len(self.data):
                c = self.data[self.i]
                self.i += 1
                if c == ESC:
                    self.do_esc()
                elif c == GS:
                    self.do_gs()
                elif c == FS:
                    self.tag(f"[?FS {chr(self.byte())!r}]")
                elif c == 0x0A:
                    self.text.append(c)
                elif c == 0x0D:
                    pass  # CR is a no-op on most ESC/POS printers
                elif c == 0x0C:
                    self.tag("[FF]\n")
                elif c == 0x09:
                    self.text.append(c)
                elif c < 0x20 or c == 0x7F:
                    self.tag(f"[\\x{c:02x}]")
                else:
                    self.text.append(c)
        except EOFError:
            self.tag("[TRUNCATED]")
        self.flush_text()
        return "".join(self.out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Decode ESC/POS bytes into readable text.")
    ap.add_argument("file", help="ESC/POS file, or - for stdin")
    ap.add_argument("--codepage", default="cp437", help="Python codec for printable bytes (default cp437)")
    ap.add_argument("--png-dir", help="save raster images as PNGs in this directory")
    args = ap.parse_args()

    if args.file == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(args.file, "rb") as f:
            data = f.read()
    text = Decoder(data, args.codepage, args.png_dir).run()
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


if __name__ == "__main__":
    main()
