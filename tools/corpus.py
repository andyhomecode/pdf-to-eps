#!/usr/bin/env python3
# corpus — run the filter over a folder of real sample documents, to check a
# change against all of them rather than one at a time.
#
# For each PDF, JPEG or PNG it writes, into the output folder:
#   <name>.txt  the decoded output (tools/escpos_preview.py)
#   <name>.png  the printout's images stitched together, as they'd print
# and prints a summary line: lines of text, images, paper length, time.
#
# With --ref, it also runs the filter as it was at that git ref and lists
# which samples print differently.
#
#   python3 tools/corpus.py                          # tests/private/
#   python3 tools/corpus.py --ref main               # what changed since main
#   python3 tools/corpus.py some.pdf other/ --out /tmp/corpus
#
# tests/private/ is git-ignored: personal samples (emails, tickets) stay local.

import argparse
import io
import os
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import escpos_preview  # noqa: E402

DOTS_PER_CM = 203 / 2.54
LINE_CM = 0.42  # Font A line with default spacing
SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png")


def samples(paths):
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if name.lower().endswith(SUFFIXES):
                    yield os.path.join(path, name)
        elif path.lower().endswith(SUFFIXES):
            yield path


def run(filter_path, sample, options):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ESCPOS_")}
    env["PPD"] = os.path.join(REPO, "ppd", "thermal-receipt.ppd")
    start = time.time()
    out = subprocess.run([sys.executable, filter_path, "1", "corpus", os.path.basename(sample), "1", options, sample],
                         capture_output=True, env=env, timeout=300).stdout
    return out, time.time() - start


def decode(data):
    """Decoded text, and the printout's images stitched into one picture."""
    with tempfile.TemporaryDirectory() as tmp:
        text = escpos_preview.Decoder(data, "cp437", tmp).run()
        picture = None
        try:
            from PIL import Image
            images = [Image.open(os.path.join(tmp, n)).convert("1") for n in sorted(os.listdir(tmp))]
            if images:
                picture = Image.new("1", (max(i.width for i in images), sum(i.height for i in images)), 1)
                y = 0
                for i in images:
                    picture.paste(i, (0, y))
                    y += i.height
        except ImportError:
            pass
    return text, picture


def main():
    ap = argparse.ArgumentParser(description="Run the filter over sample documents.")
    ap.add_argument("paths", nargs="*", default=[os.path.join(REPO, "tests", "private")])
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "pdf2escpos-corpus"))
    ap.add_argument("--ref", help="also run the filter from this git ref and report differences")
    ap.add_argument("--options", default="", help="CUPS job options, e.g. PrintMode=Text")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    ref_filter = None
    if args.ref:
        source = subprocess.run(["git", "-C", REPO, "show", f"{args.ref}:pdf2escpos.py"],
                                capture_output=True, check=True).stdout
        ref_filter = os.path.join(args.out, "ref_filter.py")
        with open(ref_filter, "wb") as f:
            f.write(source)

    found = False
    for sample in samples(args.paths):
        found = True
        name = os.path.splitext(os.path.basename(sample))[0]
        data, seconds = run(os.path.join(REPO, "pdf2escpos.py"), sample, args.options)
        text, picture = decode(data)
        with open(os.path.join(args.out, name + ".txt"), "w") as f:
            f.write(text)
        rows = 0
        if picture:
            picture.save(os.path.join(args.out, name + ".png"))
            rows = picture.height
        text_lines = sum(1 for line in text.splitlines() if "[IMG" not in line)
        cm = text_lines * LINE_CM + rows / DOTS_PER_CM
        summary = f"{name[:48]:48} {text_lines:4} lines {text.count('[IMG'):3} images {cm:6.1f} cm {seconds:5.1f}s"
        if ref_filter:
            ref_data, _ = run(ref_filter, sample, args.options)
            summary += "  same as ref" if ref_data == data else "  CHANGED vs ref"
            if ref_data != data:
                ref_text, ref_picture = decode(ref_data)
                with open(os.path.join(args.out, name + ".ref.txt"), "w") as f:
                    f.write(ref_text)
                if ref_picture:
                    ref_picture.save(os.path.join(args.out, name + ".ref.png"))
        print(summary)
    if not found:
        print(f"No samples in {', '.join(args.paths)}")
    else:
        print(f"Output in {args.out}")


if __name__ == "__main__":
    main()
