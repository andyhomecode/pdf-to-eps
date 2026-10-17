# pdf2escpos: shared improvements now, CD-S500A next, OKI ML420 later

## Hand-off notes for the thinkcentre session

- The repo is `https://github.com/andyhomecode/pdf-to-eps` (branch `main`). To get it on the thinkcentre, commit and push `IMPROVEMENTS.md` from the laptop first, then `git clone`/`git pull` there.
- Working locally on the thinkcentre removes the SSH steps. `install.sh` can install straight into `/usr/lib/cups/filter/`, and `sudo cat /etc/cups/ppd/thermal-receipt.ppd` gives the live PPD to start `ppd/thermal-receipt.ppd` from. The `.O` file next to it is CUPS's backup of the original.
- What's already on the thinkcentre (checked 2026-10-17): Ubuntu 24.04, Python 3.12.3, poppler-utils 24.02 (`pdftotext`, `pdftohtml`, `pdftoppm`), python3-pil 10.2, cups-filters 2.0. Queue `thermal-receipt` → `socket://192.168.1.16:9100`, shared, `printer-make-and-model='Thermal Receipt Printer'`. Current options: `PageSize` (Receipt80mm/58mm), `EscposCols` (32/42/48, default 48), `EscposCodepage` (cp437/cp858/latin-1). The last jobs were 2026-01-25.
- `/var/log/cups/error_log` needs `sudo`. Turn on debug logging while testing with `sudo cupsctl --debug-logging`, and turn it off afterwards.
- Before editing the filter, keep a copy of the working one, e.g. `/usr/lib/cups/filter/pdf2escpos.py.2026-10-17`, matching the reference doc's habit of dated backups.
- The untracked `istockphoto-474066854-612x612.jpg` in the repo is a handy image-print test: convert it to PDF, or print it directly, since CUPS converts images to PDF before the filter runs.

## Context

`pdf2escpos.py` runs on the thinkcentre as the CUPS filter for the `thermal-receipt` queue. The queue is shared over AirPrint and sends to the Epson TM-T20II at `socket://192.168.1.16:9100`. The deployed copy at `/usr/lib/cups/filter/pdf2escpos.py` matches the repo apart from comments. It works well, but a check of the live setup turned up these problems:

- The queue's PPD offers **Columns**, **Character Set** and **Page Size**, but the filter only reads `ESCPOS_*` environment variables, which CUPS never sets. The menus do nothing.
- The PPD sets `cupsManualCopies: True`, which means the filter has to handle copies itself. It ignores `argv[4]`, so a 3-copy job prints once.
- Control bytes from the PDF go straight to the printer. For example, Word bullets come through as `\x01`, and a stray ESC or GS byte could be read as a command. Characters that aren't in cp437 (smart quotes, dashes, CJK punctuation) print as `?`. The filter never sends `ESC t`, so it relies on the printer's default code page.
- `pdftotext -layout` output keeps wide indents and table spacing, which wrap badly at 48 columns.
- PDFs with no text (photos, scans, QR codes) print "Unable to extract text" or come out blank.
- The PPD only exists inside the README, and there's no deploy script and no tests.

Andy wants all the improvements: fixes, safe characters, smarter layout, reading the PDF's own formatting, and images. Do the changes that affect every printer first and test them on the Epson. Then add the **Citizen CD-S500A**, a 9-pin impact ESC/POS receipt printer with USB-B, likely 76 mm paper and possibly a red/black ribbon, and test it when it's hooked up. The **OKI ML420** (also USB-B, Epson FX/IBM emulation, not ESC/POS) is a later goal. Right now it can only print text from Windows using the OKI driver, nothing prints from Mac or iPhone, and the Windows driver rasterizes PDFs, which is slow and low quality compared with text. This driver can fix that.

## Design: one filter, per-printer profiles

The filter stays a **single file** (`pdf2escpos.py`), so installing it is still just a copy. Its internal pipeline:

```
PDF ─► extract (pdftohtml -xml, fallback pdftotext -layout)
    ─► document model: pages → lines (text runs with size/bold/italic/color, x-position)
    ─► layout (dedent, reflow, headings, rules, prices, header/footer removal, blank collapse)
    ─► render via PROFILE (bytes for that printer's command set)
```

**Profiles** are a dict in the filter. Each one sets: command set (`escpos` or `escp`), printer type (thermal or impact), columns per font, print width in dots and dpi, code page table (name → `ESC t n`), cut command (or none), image method, and whether it supports red.
- `epson-tm-t20ii`: thermal, 48 cols (Font A), 576 dots (check with the calibration print), cut with `ESC m` (current behavior, known to work), images with `GS v 0` in bands.
- `citizen-cd-s500a`: impact, about 40 cols (to verify), `GS V` cut, `ESC r 1` for red, images with `ESC *` 8-dot bands. Marked *unverified* until the hardware tests in phase 2.
- `oki-ml420`: added in phase 3, ESC/P.

**Where settings come from**, lowest to highest priority: profile defaults → PPD defaults (read from the file in the `$PPD` env var CUPS sets) → job options from `argv[5]` (parsed with `shlex`) → `ESCPOS_*` env vars (kept for command-line testing). Existing option names (`EscposCols`, `EscposCodepage`, `PageSize`) stay the same so the current queue keeps working. New PPD options:
- `EscposProfile` (fixed per PPD)
- `PrintMode`: Auto / Text only / Image only
- `PrintTitle`: on/off (AirPrint titles are often meaningless)

**Copies:** render the document once and write it `argv[4]` times, with a cut between copies.

## Phase 1: changes for every printer (test on the Epson now)

1. **Settings and copies** as described above. Also: a 58 mm `PageSize` chooses the 58 mm column count unless `EscposCols` is set explicitly.
2. **Safe characters**
   - Remove C0/C1 control characters, except that tabs are expanded and line feeds kept.
   - Map common Unicode characters to safe ones before encoding: smart quotes → `'`/`"`, en/em dashes → `-`, `•`/`\x01` bullets → `*`, `…` → `...`, NBSP → space, ﬁ/ﬂ ligatures → letters, `、`/`，` → `,`. Then use `unicodedata` NFKD to strip accents when the target code page lacks the character. Use `?` only as a last resort.
   - Send `ESC t n` for the selected code page (the cp437/cp858/latin-1 table lives in the profile).
3. **Read PDF formatting** with `pdftohtml -xml -i -stdout` (poppler-utils, already installed). It gives each text run's position, font size, bold/italic and color. Rules:
   - The body size is the median font size. Text ≥ 1.4× body prints double-height (`ESC !`); ≥ 2× prints double-height and double-width.
   - Bold fonts print bold (`ESC E`).
   - Red-ish text prints red (`ESC r 1`) on profiles that support it, otherwise bold.
   - A line whose center sits near the page center prints centered; a line flush to the right margin prints right-aligned.
   - If the XML is unusable, fall back to the current `pdftotext -layout` path.
4. **Smarter layout**
   - Remove the common left indent.
   - Rejoin lines that belong to one paragraph (same size, small vertical gap, previous line reaches near the right margin), then rewrap them to the column width.
   - Bullet and numbered items wrap with a hanging indent.
   - Lines like `Item ..... $9.99` or `Label     12.50` print with the label on the left and the amount right-aligned at full width.
   - A line made only of `-`, `_`, `=` or `*` becomes one full-width rule.
   - Text that repeats in the top or bottom margin on every page, and `Page N of M` or a bare page number, is dropped.
   - Runs of blank lines collapse to one; leading and trailing blanks are trimmed before the cut feed.
   - Existing markers (`[CENTER]`, `[B]`, `[U]`, `[CUT]`, …) still work.
5. **Images**
   - A page with no text, or `PrintMode=Image`, is rendered with `pdftoppm -gray -r <profile dpi> -scale-to-x <dots>`. Pillow (`python3-pil`, already on the thinkcentre) loads it, then:
     - **Prep:** auto-contrast, then a small gamma lift (set per profile) to compensate for dot gain. Impact pins spread more than thermal dots, so impact profiles get a bigger lift.
     - **Dithering** is a new PPD option `Dither`: Auto (default) / Atkinson / Floyd–Steinberg / Threshold.
       - Auto looks at the grayscale histogram. If at least ~95% of pixels are near pure black or white (QR codes, barcodes, logos, line art), it thresholds, keeping edges sharp so codes still scan. Anything else gets **Atkinson**.
       - Atkinson passes on 6/8 of the error over 6 neighbors. That gives cleaner light areas and higher contrast on thermal and impact paper than Floyd–Steinberg, which prints muddy because of dot gain. The cost is crushed shadows, which the gamma lift offsets.
       - Pillow has no Atkinson, so it's written in pure Python (about 15 lines, 1–2 s for a 576-px-wide page). Floyd–Steinberg uses Pillow's built-in `convert('1')`.
     - The profile's image method then sends the 1-bit result.
     - Add tests for the Auto choice (a QR-like fixture should threshold, a photo should get Atkinson) and an exact-pixel test of Atkinson on a small gradient.
     - Phase 2 calibration page: print the same test photo with all three methods side by side.
   - Thermal printers use `GS v 0` in bands of 256 rows. Impact printers use `ESC *` 8-dot bands with `ESC 3` line spacing set to the band height.
   - Mixed pages (text plus logo) stay text in this phase. Printing logos inline is a possible later add-on.
6. **Logging** to stderr with CUPS prefixes (`INFO:`, `DEBUG:`, `ERROR:`), so `/var/log/cups/error_log` shows the profile, the settings used and which extraction path ran. If something fails, the job still prints a short notice, as it does now.
7. **Preview tool** `tools/escpos_preview.py`: decodes the ESC/POS bytes into readable text (`[B]…[/B]`, `[2H]`, `[RED]`, `[IMG 576x312]`, `[CUT]`) and can save images as PNG. This lets output be checked without using paper.
8. **Tests** in `tests/`, using stdlib `unittest`:
   - settings priority and parsing `argv[5]`
   - character sanitizing and mapping
   - layout rules: reflow, prices, rules, header/footer removal
   - exact bytes for each profile's commands
   - copies
   - end-to-end runs on small fixture PDFs in `tests/fixtures/`: text receipt, Word-style document, image-only page, and `spe033.pdf`. Fixtures are generated with whatever local tool is available (LibreOffice headless or `cupsfilter`) and committed.
9. **Repo files**
   - `ppd/thermal-receipt.ppd`: rebuilt from the live PPD, which needs `sudo` to read and has the same options as the README version, plus the new options.
   - `install.sh`: copies the filter and PPDs to the thinkcentre and keeps `pdf2escpos.py.bak` for rollback. Then `sudo install -m 755`, `lpadmin -p <queue> -P <ppd>` and a test print. Supports `--rollback`.
   - `.gitignore` for `output*.escpos` and stray images.
   - Update the README (options, profiles, preview tool, install).
   - Fix `.copilot-instructions.md`, which says "EPS" where it means ESC/POS.
10. **Notes** (Andy asked for them):
    - `NOTES.md` in the repo: the printer list, how each one connects, the CD-S500A test checklist, and the OKI plan, including its motivation (Windows-only, rasterized PDFs).
    - A short "Receipt printers" section in `~/Dropbox/thinkcentre-reference.md`: queue names, filter path, PPDs, deploy and rollback commands. That doc currently says only "thermal printer box at 192.168.1.16".
    - A memory entry recording the OKI goal and the CD-S500A plan.

## Phase 2: CD-S500A (once it's plugged in)

Connection: **USB-B straight into the thinkcentre** if it can sit in the shoe room; the URI comes from `lpinfo -v`, `usb://Citizen/...`. Otherwise, a **Raspberry Pi running `p910nd`** (raw port 9100, one port per printer, so the same Pi can also drive the OKI) with `socket://<pi>:9100`. The filter doesn't care which.

Steps:
1. Create `ppd/citizen-cd-s500a.ppd` (`EscposProfile=citizen-cd-s500a`) and a queue `receipt-citizen`, shared over AirPrint.
2. Print a calibration page from the filter (`PrintMode=Calibrate`): a column ruler for each font, a code page sample, bold, double-height and red samples, a dot-width ruler image, then a cut.
3. Fix the profile based on what prints: column counts, dots, image density and band alignment, the cut command (some units have no autocutter, so it falls back to a feed), and red support.
4. Test real prints from iPhone and Mac, and update `NOTES.md` and the reference doc.

## Phase 3: OKI ML420 (later)

Add an `escp` command set to the renderer:
- 80/136 columns depending on pitch
- form feed per page instead of a cut
- `ESC E` bold, `ESC W` double-width
- `ESC *` 8-pin graphics for image pages
- the code page via its ESC/P command

Give the OKI its own PPD and queue. It connects by USB-B, either to the thinkcentre or to the same Pi. The result: Mac and iPhone can print to the OKI over AirPrint, text prints as fast native text, and only image pages are rasterized.

## Critical files

- `pdf2escpos.py`: refactor into extract → model → layout → render, with profiles and settings resolution. Reuse the existing `init_seq`, alignment and style helpers, `emit_line` marker handling and the error-notice paths.
- `ppd/*.ppd`, `install.sh`, `tools/escpos_preview.py`, `tests/`, `NOTES.md`, `README.md`.
- On the thinkcentre (through `install.sh`, after you approve): `/usr/lib/cups/filter/pdf2escpos.py` and the `thermal-receipt` queue's PPD.

## Verification

1. `python3 -m unittest discover tests`, run locally.
2. Run the filter locally on each fixture with different settings, check the output with `tools/escpos_preview.py`, and compare against the current filter's output for `spe033.pdf`: same text, cleaner layout.
3. Check the CUPS path locally with `cupsfilter -p ppd/thermal-receipt.ppd -m application/vnd.cups-raw fixture.pdf`, so the `$PPD` and `argv[5]` handling runs under real CUPS.
4. Deploy with `install.sh` (the old filter is kept for rollback). Print from an iPhone (AirPrint) and from the command line: `lp -d thermal-receipt -n 2 -o EscposCols=42 file.pdf`, a photo, and a receipt PDF. Check `error_log` for the `INFO:` lines.
5. Phase 2 checklist on the CD-S500A, as above.
