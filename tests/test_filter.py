#!/usr/bin/env python3
# Tests for pdf2escpos.py. Run from the repo root:
#   python3 -m unittest discover tests

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import pdf2escpos as f  # noqa: E402

sys.path.insert(0, os.path.join(REPO, "tools"))
import escpos_preview  # noqa: E402

FILTER = os.path.join(REPO, "pdf2escpos.py")
PPD = os.path.join(REPO, "ppd", "thermal-receipt.ppd")
FIXTURES = os.path.join(REPO, "tests", "fixtures")
RECEIPT_PDF = os.path.join(FIXTURES, "receipt.pdf")
INVOICE_PDF = os.path.join(FIXTURES, "sample-invoice.pdf")
TEXTBOOK_PDF = os.path.join(FIXTURES, "sample-textbook.pdf")
PHOTO_PDF = os.path.join(FIXTURES, "photo.pdf")
QR_PDF = os.path.join(FIXTURES, "qr.pdf")
EMAIL_PDF = os.path.join(FIXTURES, "email.pdf")
NOTICE_PDF = os.path.join(FIXTURES, "notice.pdf")
WEBPAGE_PDF = os.path.join(FIXTURES, "webpage.pdf")


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

    def test_superscript_letters(self):
        # 20th and 22nd as iOS writes them; superscript digits stay
        self.assertEqual(f.sanitize("20\u1d57\u02b0 22\u207f\u1d48 10mm\u00b2", "cp437"), "20th 22nd 10mm\u00b2")

    def test_invisible(self):
        self.assertEqual(f.sanitize("a\u200bb\u00adc\ufeff\ufffd", "cp437"), "abc?")


class TestBytes(unittest.TestCase):
    def test_init_sets_code_page(self):
        s = f.resolve_settings(argv(options="EscposCodepage=cp858"), {})
        self.assertEqual(f.init_seq(s), b"\x1b@\x1bM\x00\x1b2\x1bt\x13")

    def test_cut_marker_uses_profile_cut(self):
        s = f.resolve_settings(argv(), {})
        doc = f.render_document(f.layout_plain("a\n[CUT]\nb", s), "", s)
        self.assertNotIn(b"\x1dV", doc)
        self.assertEqual(doc.count(b"\x1bm"), 2)  # marker + end of job


class TestEndToEnd(unittest.TestCase):
    def run_filter(self, copies="1", options="", path=RECEIPT_PDF):
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
        # Every byte below 0x20 must be LF or part of a known command,
        # which the preview decoder checks.
        for path in (RECEIPT_PDF, INVOICE_PDF, TEXTBOOK_PDF):
            text = escpos_preview.Decoder(self.run_filter(path=path).stdout, "cp437", None).run()
            self.assertNotIn("[\\x", text, path)
            self.assertNotIn("[?", text, path)

    def test_options_reach_output(self):
        out = self.run_filter(options="EscposCodepage=cp858").stdout
        self.assertIn(b"\x1bt\x13", out)

    def test_not_a_pdf_prints_notice(self):
        r = self.run_filter(path=os.path.join(REPO, "test.txt"))
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"Unable to extract text", r.stdout)


def preview(path, options=""):
    """Run the filter on a fixture and decode the output to tagged text."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ESCPOS_")}
    env["PPD"] = PPD
    out = subprocess.run([sys.executable, FILTER, "1", "andy", "Test", "1", options, path],
                         capture_output=True, env=env, timeout=60).stdout
    return escpos_preview.Decoder(out, "cp437", None).run()


class TestLayoutHelpers(unittest.TestCase):
    def test_collapse_fake_bold(self):
        self.assertEqual(f.collapse_repeats("InInvvoicoicee"), "Invoice")
        self.assertEqual(f.collapse_repeats("CoCoffffeeee"), "Coffee")

    def test_join_lines_mends_hyphens(self):
        self.assertEqual(f.join_lines(["The re-", "ceptors in"]), "The receptors in")
        self.assertEqual(f.join_lines(["range of 40-", "60 degrees"]), "range of 40- 60 degrees")
        self.assertEqual(f.join_lines(["Word-", "Processor"]), "Word- Processor")

    def test_empty_run_is_bullet(self):
        xml = (b'<pdf2xml><page number="1" top="0" left="0" height="800" width="600">'
               b'<fontspec id="0" size="16" family="Arial" color="#000000"/>'
               b'<text top="100" left="85" width="13" height="17" font="0"></text>'
               b'<text top="100" left="116" width="200" height="17" font="0">Support Mp3 \x01</text>'
               b'<text top="140" left="85" width="13" height="17" font="0"></text>'
               b'</page></pdf2xml>')
        page = f.extract_pages(xml)[0]
        self.assertEqual([s.text for s in page.segments], ["\u2022 Support Mp3 \u2022"])

    def test_bold_from_font_name(self):
        xml = (b'<pdf2xml><page number="1" top="0" left="0" height="800" width="600">'
               b'<fontspec id="0" size="17" family="PXAAAC+Gelasio_700wght" color="#ed1c24"/>'
               b'<text top="100" left="85" width="100" height="21" font="0">Description</text>'
               b'</page></pdf2xml>')
        seg = f.extract_pages(xml)[0].segments[0]
        self.assertTrue(seg.bold)
        self.assertTrue(seg.red)

    def test_bold_font_names(self):
        self.assertTrue(f.is_bold_font("AAAAAB+.SFUI-Regular_wdth_opsz110000_GRAD_wght2BC0000"))  # 700
        self.assertTrue(f.is_bold_font("AAAAAB+.SFUI-Regular_wdth_opsz110000_GRAD_wght2580000"))  # 600
        self.assertFalse(f.is_bold_font("AAAAAC+.SFUI-Regular_wdth_opsz110000_GRAD_wght"))
        self.assertFalse(f.is_bold_font("X+.SFUI-Regular_wght1900000"))  # 400
        self.assertTrue(f.is_bold_font("PXAAAC+Gelasio_700wght"))
        self.assertTrue(f.is_bold_font("Helvetica-Bold"))
        self.assertFalse(f.is_bold_font("Helvetica"))

    def test_wrap_words(self):
        words = [("PLEASE", True), ("TAKE", True), ("NOTICE", True), ("that", False), ("Special", False)]
        self.assertEqual(f.wrap_words(words, 24),
                         [[("PLEASE TAKE NOTICE", True), (" that", False)], [("Special", False)]])
        # Hanging indent, and a long word broken at a hyphen
        self.assertEqual(f.wrap_words([("*", False), ("aa", False), ("bbbb-cccc", False)], 8, hang=2),
                         [[("* aa", False)], [("  bbbb-", False)], [("  cccc", False)]])

    def test_split_number_is_not_a_list_item(self):
        seg = lambda text, top: f.Segment(text, 50, 50 + 7 * len(text), top, top + 20, 19, False, False, 1, top)
        block = f.Block([seg("documents pursuant to Section 24-", 0), seg("112. Learn about what to send.", 24)])
        self.assertEqual(len(f.split_paragraphs(block)), 1)
        self.assertEqual(" ".join(w for w, _ in f.join_words(block.segs)),
                         "documents pursuant to Section 24-112. Learn about what to send.")

    def test_fit_row(self):
        seg = lambda text, left, right: f.Segment(text, left, right, 0, 10, 10, False, False, 1, 1)
        self.assertEqual(f.fit_row([seg("Total", 0, 50), seg("$9.99", 400, 450)], 20),
                         [("Total          $9.99", 0)])
        self.assertEqual(f.fit_row([seg("Item ...... $9.99", 0, 100)], 20),
                         [("Item           $9.99", 0)])
        self.assertEqual(f.fit_row([seg("Bank address:", 0, 50), seg("231 Swanston St, Melbourne", 300, 450)], 20),
                         [("Bank address:", 0), ("  231 Swanston St, Melbourne", 2)])


class TestLayout(unittest.TestCase):
    def test_receipt(self):
        text = preview(RECEIPT_PDF, "PrintTitle=false")
        self.assertNotIn("[U]Test", text)
        self.assertIn("[CODEPAGE 0][CENTER][MODE 2H 2W][B]CORNER CAFE", text)
        self.assertIn("Latte" + " " * 38 + "$4.50", text)
        self.assertIn("-" * 48 + "\n", text)
        self.assertIn("[B]Total" + " " * 38 + "$7.75", text)
        self.assertIn("* Free refills on drip coffee", text)
        self.assertIn("Thank you for visiting. This paragraph is long\nenough", text)
        self.assertNotRegex(text, r"\n1\n")  # page number dropped

    def test_receipt_narrow(self):
        text = preview(RECEIPT_PDF, "EscposCols=32")
        self.assertIn("Latte" + " " * 22 + "$4.50", text)

    def test_invoice(self):
        text = preview(INVOICE_PDF)
        self.assertIn("[MODE 2H 2W][B]Invoice\n", text)  # fake bold undone
        self.assertIn("Invoice date:" + " " * 23 + "Nov 26, 2016", text)
        self.assertIn("Total" + " " * 32 + "USD $950.00", text)
        self.assertIn("YesLogic Pty. Ltd.\n7 / 39 Bouverie St\n", text)  # address kept together
        self.assertNotRegex(text, r"\n +\n")  # no lines of only spaces

    def test_inline_bold(self):
        text = preview(NOTICE_PDF)
        self.assertIn("[B]PLEASE TAKE NOTICE[/B] that Special Meetings of", text)
        self.assertIn("[B]BY ORDER OF THE MAYOR OF THE VILLAGE\n[/B]", text)
        self.assertEqual(text.count("[B]"), 2)

    def test_webpage(self):
        # Few words per line on the 80mm page, as iPhone prints web pages
        text = preview(WEBPAGE_PDF, "PrintTitle=false")
        self.assertIn("[B]Citizens Air Complaint Program\n", text)  # tight leading kept in order
        self.assertIn("Idling emissions from gasoline and diesel motor\nvehicle engines", text)
        # The second paragraph runs onto page 2 ("in our complaint program...")
        # and is joined back up with no blank line
        self.assertIn("enforcement efforts, you can also participate in\nour complaint program, which", text)
        self.assertIn("1. Questions and comments submitted by email\n   will be answered in ten business days.\n"
                      "2. Submissions are reviewed", text)

    def test_textbook(self):
        text = preview(TEXTBOOK_PDF)
        self.assertIn("The receptors in the skin, the so", text)  # "re-" + "ceptors" mended
        self.assertIn("This is a sample document to showcase page-based", text)  # sidenote reflowed
        self.assertIn("[B]Cutaneous receptors\n[/B]Sensory information", text)
        self.assertIn("corpuscles and Merkel's disks.", text)
        for label in ("Epidermis", "Papillary Ridges", "From Wikibooks"):
            self.assertNotIn(label, text)  # diagram labels and running headers dropped


@unittest.skipIf(f.Image is None, "python3-pil not installed")
class TestImages(unittest.TestCase):
    def test_auto_dither_choice(self):
        s = f.resolve_settings(argv(), {})
        qr = f.page_image(QR_PDF, 1, s.dots)
        photo = f.page_image(PHOTO_PDF, 1, s.dots)
        self.assertEqual(f.choose_dither(f.ImageOps.autocontrast(qr, cutoff=1), "auto"), "threshold")
        self.assertEqual(f.choose_dither(f.ImageOps.autocontrast(photo, cutoff=1), "auto"), "atkinson")
        self.assertEqual(f.choose_dither(photo, "floyd-steinberg"), "floyd-steinberg")

    def test_page_image_is_paper_width(self):
        img = f.page_image(PHOTO_PDF, 1, 576)
        self.assertEqual(img.size, (576, 432))  # 400x300 image scaled to 576 wide

    def test_atkinson_exact(self):
        # 0, 64, 128, 255: 64 goes black and passes +8 right; 136 goes white
        # and passes -15 on; 248 goes white
        img = f.Image.new("L", (4, 1))
        img.putdata([0, 64, 128, 255])
        self.assertEqual(list(f.atkinson(img).getdata()), [0, 0, 255, 255])

    def test_atkinson_spreads_error_down(self):
        # Mid gray: about half the dots black, and not in a solid block
        img = f.Image.new("L", (16, 16), 128)
        dots = list(f.atkinson(img).getdata())
        black = dots.count(0)
        self.assertTrue(80 <= black <= 176, black)

    def test_raster_commands(self):
        img = f.Image.new("1", (16, 300), 255)
        img.putpixel((0, 0), 0)
        out = f.raster_commands(img)
        # Two bands: 256 rows then 44 rows, 2 bytes per row; 1 = black
        self.assertEqual(out[:8], b"\x1dv0\x00\x02\x00\x00\x01")
        self.assertEqual(out[8:10], b"\x80\x00")
        second = 8 + 2 * 256
        self.assertEqual(out[second:second + 8], b"\x1dv0\x00\x02\x00\x2c\x00")
        self.assertEqual(len(out), 8 + 512 + 8 + 88)

    def test_image_only_pdf_prints_image(self):
        text = preview(PHOTO_PDF)
        self.assertIn("[IMG 576x256]", text)
        self.assertIn("[IMG 576x176]", text)

    def test_print_mode(self):
        self.assertIn("[IMG 576x", preview(RECEIPT_PDF, "PrintMode=Image"))
        self.assertNotIn("[IMG", preview(RECEIPT_PDF))
        text = preview(PHOTO_PDF, "PrintMode=Text")
        self.assertNotIn("[IMG", text)
        self.assertIn("This PDF has no text", text)

    def test_jpeg_input_prints_whole_upright(self):
        # Stored 300x400 sideways with EXIF orientation 6: prints 400x300 upright, scaled to 576
        text = preview(os.path.join(FIXTURES, "rotated.jpg"))
        self.assertIn("[IMG 576x256][IMG 576x176]", text)
        self.assertNotIn("Test", text)  # no title on photos

    def test_image_only_pdf_has_no_title(self):
        self.assertNotIn("Test", preview(PHOTO_PDF))
        self.assertIn("[U]Test[/U]", preview(RECEIPT_PDF))

    def test_png_with_transparency(self):
        # 200x200 QR blocks; transparent areas are white, and it stays sharp
        text = preview(os.path.join(FIXTURES, "logo.png"))
        self.assertIn("[IMG 576x256][IMG 576x256][IMG 576x64]", text)

    def test_embedded_images(self):
        text = preview(EMAIL_PDF)
        # Photo full width, QR in proportion (150 of 451pt); the tracking pixel
        # and the banner behind text are skipped
        self.assertIn("Your Ticket", text)
        self.assertIn("[IMG 576x256][IMG 576x63]\n[IMG 576x191]\n[B]Text over a banner image", text)
        self.assertEqual(text.count("[IMG"), 3)

    def test_embedded_qr_is_sharp_and_centered(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ESCPOS_")}
        out = subprocess.run([sys.executable, FILTER, "1", "a", "t", "1", "", EMAIL_PDF],
                             capture_output=True, env=env, timeout=60).stdout
        with tempfile.TemporaryDirectory() as tmp:
            escpos_preview.Decoder(out, "cp437", tmp).run()
            qr = f.Image.open(os.path.join(tmp, "image03.png")).convert("L")
        left, top, right, bottom = f.ImageOps.invert(qr).getbbox()
        self.assertAlmostEqual((left + right) / 2, 288, delta=4)
        # Thresholded, not dithered: whole modules, so few isolated dots
        px = qr.load()
        lonely = sum(1 for y in range(1, qr.height - 1) for x in range(left + 1, right - 1)
                     if all(px[x, y] != px[x + dx, y + dy] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
        self.assertLess(lonely, 10)

    def test_embedded_images_off(self):
        text = preview(EMAIL_PDF, "EmbeddedImages=False")
        self.assertNotIn("[IMG", text)
        self.assertIn("See you soon!", text)

    def test_no_files_left_beside_input(self):
        # pdftohtml writes extracted images next to its output; they must not
        # land next to the input (a CUPS spool file)
        with tempfile.TemporaryDirectory() as tmp:
            pdf = os.path.join(tmp, "job.pdf")
            shutil.copy(EMAIL_PDF, pdf)
            subprocess.run([sys.executable, FILTER, "1", "a", "t", "1", "", pdf],
                           capture_output=True, timeout=60)
            self.assertEqual(os.listdir(tmp), ["job.pdf"])

    def test_58mm_images_are_narrower(self):
        self.assertIn("[IMG 416x", preview(PHOTO_PDF, "PageSize=Receipt58mm"))


if __name__ == "__main__":
    unittest.main()
