#!/usr/bin/env python3
# Tests for pdf2escpos.py. Run from the repo root:
#   python3 -m unittest discover tests

import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import pdf2escpos as f  # noqa: E402

sys.path.insert(0, os.path.join(REPO, "tools"))
import escpos_preview  # noqa: E402

FILTER = os.path.join(REPO, "pdf2escpos.py")
PPD = os.path.join(REPO, "ppd", "thermal-receipt.ppd")
SAMPLE_PDF = os.path.join(REPO, "spe033.pdf")


def argv(copies="1", options=""):
    return ["pdf2escpos.py", "1", "andy", "title", copies, options, "file.pdf"]


class TestSettings(unittest.TestCase):
    def test_parse_options(self):
        opts = f.parse_options('EscposCols=42 PageSize=Receipt58mm job-name="a b" fitplot')
        self.assertEqual(opts["EscposCols"], "42")
        self.assertEqual(opts["PageSize"], "Receipt58mm")
        self.assertEqual(opts["job-name"], "a b")
        self.assertEqual(opts["fitplot"], "true")

    def test_parse_options_bad_quotes(self):
        self.assertEqual(f.parse_options('EscposCols=42 job-name="oops')["EscposCols"], "42")

    def test_read_ppd_defaults(self):
        d = f.read_ppd_defaults(PPD)
        self.assertEqual(d["EscposCols"], "48")
        self.assertEqual(d["EscposCodepage"], "cp437")
        self.assertEqual(d["PageSize"], "Receipt80mm")

    def test_profile_defaults(self):
        s = f.resolve_settings(argv(), {})
        self.assertEqual(s.profile_name, "epson-tm-t20ii")
        self.assertEqual((s.cols, s.codepage, s.codepage_n, s.copies), (48, "cp437", 0, 1))

    def test_priority(self):
        # PPD says 48, job options say 42, env says 32: env wins, then options
        self.assertEqual(f.resolve_settings(argv(options="EscposCols=42"), {"PPD": PPD}).cols, 42)
        env = {"PPD": PPD, "ESCPOS_COLS": "32"}
        self.assertEqual(f.resolve_settings(argv(options="EscposCols=42"), env).cols, 32)

    def test_58mm_limits_columns(self):
        s = f.resolve_settings(argv(options="PageSize=Receipt58mm"), {"PPD": PPD})
        self.assertEqual(s.cols, 35)
        s = f.resolve_settings(argv(options="PageSize=Receipt58mm EscposCols=32"), {})
        self.assertEqual(s.cols, 32)

    def test_codepage(self):
        s = f.resolve_settings(argv(options="EscposCodepage=cp858"), {})
        self.assertEqual((s.codec, s.codepage_n), ("cp858", 19))
        s = f.resolve_settings(argv(options="EscposCodepage=latin-1"), {})
        self.assertEqual((s.codec, s.codepage_n), ("cp1252", 16))

    def test_bad_values_fall_back(self):
        s = f.resolve_settings(argv(copies="lots", options="EscposCols=abc EscposCodepage=jis"), {})
        self.assertEqual((s.cols, s.codepage, s.copies), (48, "cp437", 1))
        self.assertEqual(f.resolve_settings(argv(copies="9999"), {}).copies, 1)
        self.assertEqual(f.resolve_settings(argv(copies="3"), {}).copies, 3)


class TestSanitize(unittest.TestCase):
    def test_controls_removed(self):
        self.assertEqual(f.sanitize("a\x1b@b\x1dVc\x07\x7f\x9b", "cp437"), "a@bVc")

    def test_word_bullet(self):
        self.assertEqual(f.sanitize("\x01    Support", "cp437"), "*    Support")

    def test_tabs_and_newlines(self):
        self.assertEqual(f.sanitize("a\tb\n", "cp437"), "a       b\n")

    def test_punctuation_mapped(self):
        s = "\u201cHi\u201d \u2018x\u2019 a\u2013b\u2014c \u2022 \u2026 \ufb01"
        self.assertEqual(f.sanitize(s, "cp437"), "\"Hi\" 'x' a-b-c * ... fi")

    def test_kept_when_code_page_has_it(self):
        # cp437 has é; cp1252 has smart quotes and the euro sign
        self.assertEqual(f.sanitize("caf\u00e9", "cp437"), "caf\u00e9")
        self.assertEqual(f.sanitize("\u201cx\u201d \u20ac", "cp1252"), "\u201cx\u201d \u20ac")

    def test_accents_stripped(self):
        self.assertEqual(f.sanitize("\u0141\u00f3d\u017a", "cp437"), "L\u00f3dz")

    def test_cjk(self):
        self.assertEqual(f.sanitize("\u4e2d\u3001\uff0c", "cp437"), "?,,")

    def test_invisible(self):
        self.assertEqual(f.sanitize("a\u200bb\u00adc\ufeff\ufffd", "cp437"), "abc?")


class TestBytes(unittest.TestCase):
    def test_init_sets_code_page(self):
        s = f.resolve_settings(argv(options="EscposCodepage=cp858"), {})
        self.assertEqual(f.init_seq(s), b"\x1b@\x1bM\x00\x1b2\x1bt\x13")

    def test_cut_marker_uses_profile_cut(self):
        s = f.resolve_settings(argv(), {})
        doc = f.render_document(["[CUT]"], "", s)
        self.assertNotIn(b"\x1dV", doc)
        self.assertEqual(doc.count(b"\x1bm"), 2)  # marker + end of job


class TestEndToEnd(unittest.TestCase):
    def run_filter(self, copies="1", options="", path=SAMPLE_PDF):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ESCPOS_")}
        env["PPD"] = PPD
        return subprocess.run(
            [sys.executable, FILTER, "1", "andy", "Test", copies, options, path],
            capture_output=True, env=env, timeout=60)

    def test_copies(self):
        one = self.run_filter("1").stdout
        three = self.run_filter("3").stdout
        self.assertEqual(three, one * 3)
        self.assertEqual(three.count(b"\x1bm"), 3)

    def test_no_raw_controls(self):
        # spe033.pdf has Word \x01 bullets. Every byte below 0x20 must be LF,
        # tab or part of a known command, which the preview decoder checks.
        text = escpos_preview.Decoder(self.run_filter().stdout, "cp437", None).run()
        self.assertNotIn("[\\x", text)
        self.assertNotIn("[?", text)
        self.assertIn("*    Support Mp3", text)

    def test_options_reach_output(self):
        out = self.run_filter(options="EscposCodepage=cp858").stdout
        self.assertIn(b"\x1bt\x13", out)

    def test_not_a_pdf_prints_notice(self):
        r = self.run_filter(path=os.path.join(REPO, "test.txt"))
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"Unable to extract text", r.stdout)


if __name__ == "__main__":
    unittest.main()
