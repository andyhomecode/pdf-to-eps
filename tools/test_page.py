#!/usr/bin/env python3
# test_page — a raw ESC/POS test page for checking a printer profile: the
# column width, bold, red, double sizes, underline, code pages and the cut.
# Each sample names the command it uses, so what prints says what works.
#
# Usage:
#   python3 tools/test_page.py --profile citizen-cd-s500a | lp -d receipt-citizen -o raw
#   python3 tools/test_page.py | python3 tools/escpos_preview.py -

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pdf2escpos as f  # noqa: E402

RULER_COLS = 48
SAMPLE = "café üñ £5 ½ ¿¡ €10"


def ruler(cols: int) -> str:
    """....:....1....:....2 ... one character per column, the tens numbered."""
    return "".join(str(n // 10 % 10) if n % 10 == 0 else ":" if n % 5 == 0 else "."
                   for n in range(1, cols + 1))


def test_page(profile_name: str) -> bytes:
    profile = f.PROFILES[profile_name]
    out = bytearray(f.ESC + b"@")

    def line(text: str = "", codec: str = "ascii") -> None:
        out.extend(text.encode(codec, errors="replace") + b"\n")

    line(f"Test page: {profile_name}")
    line(f"Profile says {profile['cols']} columns.")
    line()
    line(f"Ruler, {RULER_COLS} columns. Where it wraps")
    line("is the printer's width:")
    line(ruler(RULER_COLS))
    line()
    for name in ("Font A", "Font B"):
        out.extend(f.ESC + b"M" + (f.FONT_A if name == "Font A" else f.FONT_B))
        line(f"{name} (ESC M):")
        line(ruler(RULER_COLS))
    out.extend(f.ESC + b"M" + f.FONT_A)
    line()
    line("Normal text")
    out.extend(f.bold_on()); line("Bold (ESC E 1)"); out.extend(f.bold_off())
    out.extend(f.red_on()); line("Red (ESC r 1)"); out.extend(f.red_off())
    out.extend(b"Black, " + f.red_on() + b"red" + f.red_off() + b", black in one line\n")
    out.extend(f.underline_on()); line("Underlined (ESC - 1)"); out.extend(f.underline_off())
    for mode, name in ((0x10, "Double height"), (0x20, "Double width"), (0x30, "Double size")):
        out.extend(f.ESC + b"!" + bytes([mode])); line(f"{name} (ESC ! {mode})")
    out.extend(f.ESC + b"!" + b"\x00")
    line()
    line("Code pages (ESC t n):")
    for name, (codec, n) in profile["codepages"].items():
        out.extend(f.ESC + b"t" + bytes([n]))
        line(f"{name} ({n}): {SAMPLE}", codec)
    out.extend(f.ESC + b"t" + bytes([profile["codepages"][profile["default_codepage"]][1]]))
    line()
    line(f"Cut ({profile['cut'].hex(' ')}) after 6 lines:")
    out.extend(f.lf(6) + profile["cut"])
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a raw ESC/POS test page to stdout.")
    ap.add_argument("--profile", default=f.DEFAULT_PROFILE, choices=sorted(f.PROFILES))
    args = ap.parse_args()
    sys.stdout.buffer.write(test_page(args.profile))


if __name__ == "__main__":
    main()
