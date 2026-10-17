# pdf2escpos

A CUPS filter that prints PDFs, photos and images on an ESC/POS receipt printer, so an Epson TM-T20II shared over AirPrint works from an iPhone or Mac like any other printer.

It handles two kinds of document differently:
- **Pages already laid out for the receipt** print **as drawn**. An iPhone or Mac lays out what it prints on the queue's 80mm page, so the PDF page is exactly the paper's width. The page is rendered 1:1 at 576 dots and matches the phone's print preview: its fonts, layout, logos (vector ones too), photos and QR codes. Text is thresholded so it stays crisp, and the page's photos are dithered.
- **Other documents** (A4 or Letter PDFs) are read for their text, layout and fonts and printed as native printer text, reflowed to the 48-column roll. Images in them print in place, and pages without text print as images.

It runs on the ThinkCentre server as the filter for the `thermal-receipt` queue. `NOTES.md` covers the printers, how they're connected and what's planned next.

## What it does

**Text layout** for pages that aren't receipt-width, or every page with `PrintMode=Text` (from `pdftohtml -xml`, falling back to `pdftotext -layout`):
- Paragraphs are rejoined and rewrapped to the paper width, and words hyphenated at line ends are mended.
- Bullet and numbered items wrap with a hanging indent. Word's Symbol-font bullets print as `*`.
- Label/value rows, table rows and dot-leader prices (`Latte ...... $4.50`) print with the value right-aligned. Lines of `-`, `_`, `=` or `*` print as one full-width rule.
- Short-line columns, such as an address, keep their line breaks.
- Headings print double height (1.4× the body size) or double size (2×). Bold text prints bold, including bold words inside a paragraph (recognised from `<b>` markup, font names and variable-font weights such as iOS's system font). Red text prints red on printers that have it, otherwise bold. Centered and right-aligned lines keep their alignment.
- Page numbers, running headers and footers, and small diagram labels are left out. Fake bold (text drawn twice) is undone.
- Control bytes are stripped, and characters the printer's code page lacks are mapped (smart quotes, dashes, `…`, ligatures) or have their accents removed. `?` is the last resort.

**Images:** JPEG and PNG files, images embedded in PDFs (logos, photos and QR codes in emails and tickets), pages with nothing but drawing, or every page with `PrintMode=Image`:
- Photos and image files are turned upright from their EXIF orientation and scaled to the full paper width.
- Embedded images print where they sit in the text, at their size relative to the text (at least 80% of the content width prints full width, and nothing prints narrower than a quarter of the paper), keeping their alignment. They're cropped from the rendered page, so they print exactly as drawn. Images under 12pt (spacers, tracking pixels), images with text printed over them, and logos repeated in the page margins are skipped. Vector drawings (SVG logos, charts) aren't detected.
- Dithered to 1 bit. `Auto` thresholds images that are almost all black and white, so QR codes and logos stay sharp. Everything else gets Atkinson dithering plus a gamma lift for thermal dot gain.
- Sent as `GS v 0` raster bands. Photos print without a title line.

**Jobs:**
- Copies: the PPD sets `cupsManualCopies`, and the filter prints each copy with its own cut.
- The job title is printed (underlined, centered) above documents unless `PrintTitle=False`.
- Markers in the PDF's text still work: `[CENTER]`, `[LEFT]`, `[RIGHT]`, `[B]…[/B]`, `[U]…[/U]` at the start of a line, and `[CUT]` on a line by itself.

## Options

Settings come from, lowest to highest priority: the printer profile, the PPD's defaults, the job's options, and `ESCPOS_*` environment variables (for command-line testing).

| PPD option | Values | Default |
|---|---|---|
| `EscposCols` (Columns) | 32, 42, 48 | 48 |
| `EscposCodepage` (Character Set) | cp437, cp858, latin-1 | cp437 |
| `PageSize` | Main queue: Receipt80mm, Receipt58mm (58mm caps columns at 35 and images at 416 dots). Text queue: Letter, A4 | Receipt80mm; Letter on the text queue |
| `PrintMode` | Auto (receipt-width pages as drawn, others laid out as text), Text (lay out every page as text, reflowed), Image (every page as drawn) | Auto |
| `Dither` | Auto, Atkinson, Floyd-Steinberg, Threshold | Auto |
| `EmbeddedImages` (Print Images in Documents) | True, False | True |
| `PrintTitle` | True, False | True |

AirPrint clients (iPhone, Mac) only show standard options such as copies and Scaling. For their jobs, change a default on the CUPS web page: http://localhost:631/printers/thermal-receipt, Administration → Set Default Options. Linux print dialogs show the menus under Printer Options, and `lp -o Name=Value` sets them per job.

Environment variables: `ESCPOS_PROFILE`, `ESCPOS_COLS`, `ESCPOS_CODEPAGE`, plus `ESCPOS_LEFT`, `ESCPOS_RIGHT` (margin spaces, 0-50), `ESCPOS_CUT_FEED_LINES` (0-20, default 6), `ESCPOS_HEADER` and `ESCPOS_FOOTER`.

## Printer profiles

The `PROFILES` dict at the top of `pdf2escpos.py` holds what differs between printers: columns, print width in dots, code page numbers for `ESC t`, the cut command, red support and image gamma. `EscposProfile` picks one (default `epson-tm-t20ii`).

| Profile | Printer | Status |
|---|---|---|
| `epson-tm-t20ii` | Epson TM-T20II thermal, 80mm, 203 dpi | In use |
| `citizen-cd-s500a` | Citizen CD-S500A impact, red/black ribbon | Planned (see NOTES.md) |
| `oki-ml420` | OKI ML420 dot matrix, ESC/P | Planned (see NOTES.md) |

## Install

Needs `python3`, `poppler-utils` (`pdftohtml`, `pdftotext`, `pdftoppm`) and `python3-pil` (Pillow, for images; text prints without it).

```bash
sudo apt install python3 poppler-utils python3-pil

# First time only: create the queue with the PPD
sudo lpadmin -p thermal-receipt -E -v socket://192.168.1.16:9100 -P ppd/thermal-receipt.ppd
sudo lpadmin -p thermal-receipt -o printer-is-shared=true
# The text queue: same printer and PPD, Letter paper, so apps lay out a normal page
# and the filter reflows it
sudo lpadmin -p thermal-receipt-text -E -v socket://192.168.1.16:9100 -P ppd/thermal-receipt-text.ppd \
    -D "Thermal Receipt (text)" -o printer-is-shared=true -o PageSize=Letter -o PageRegion=Letter
sudo cupsctl --share-printers
sudo systemctl enable --now avahi-daemon   # AirPrint discovery

# Install or update the filter and PPD
sudo ./install.sh                  # filter, and ppd/<queue>.ppd on both queues
sudo ./install.sh --filter-only    # filter only
sudo ./install.sh --test tests/fixtures/receipt.pdf   # and print a test page
sudo ./install.sh --rollback       # back to the previous filter and PPD
```

`install.sh` won't install a filter that doesn't compile or a PPD that fails `cupstestppd`. It updates both receipt queues (and skips one that doesn't exist), and CUPS keeps each queue's own defaults. Each install keeps the previous filter as `/usr/lib/cups/filter/pdf2escpos.py.bak` and each queue's previous PPD as `/etc/cups/ppd/<queue>.ppd.bak`.

**Two queues, one printer.** `thermal-receipt` defaults to the 80mm paper: apps lay pages out for the receipt and they print as drawn. `thermal-receipt-text` ("Thermal Receipt (text)") has Letter and A4 paper: apps lay out a normal page, and since it isn't 80mm wide the filter reflows it as printer text, using much less paper. Each queue has its own PPD with only its own paper sizes (`ppd/thermal-receipt.ppd`, `ppd/thermal-receipt-text.ppd`; a test keeps the rest of them identical). One PPD with all four sizes doesn't work: CUPS then reports Letter as the loaded paper, and an iPhone offers only loaded paper, so the main queue would print as text too. It needs a real terminal for `sudo`.

The PPD sends `application/pdf`, `image/jpeg` and `image/png` straight to the filter. Images have to skip CUPS's own image filter, which would crop a photo to fill the long receipt page.

## Testing

`tools/corpus.py` runs the filter over a folder of real documents (default `tests/private/`, which git ignores, for personal emails and tickets). It saves each one's decoded output and a picture of the printout, and with `--ref main` lists which documents print differently from that version. Run it before committing a layout change.

```bash
python3 -m unittest discover tests

# Run the filter by hand (argv: job user title copies options file)
python3 pdf2escpos.py 1 me "Title" 1 "EscposCols=42" tests/fixtures/receipt.pdf > out.escpos

# Read the output without printing: [B]…[/B], [2H], [CENTER], [IMG 576x256], [CUT] …
python3 tools/escpos_preview.py out.escpos
python3 tools/escpos_preview.py --png-dir /tmp/imgs out.escpos   # also save images

# Send it to the printer directly
lp -d thermal-receipt -o raw out.escpos
```

Fixtures are in `tests/fixtures/`. `receipt.pdf` is built from `receipt.ps` with `ps2pdf`, and the image fixtures (including `email.pdf`, text with embedded images) come from `make_image_fixtures.py`. `sample-invoice.pdf` and `sample-textbook.pdf` are real-world layouts.

The filter logs to the CUPS error log as `pdf2escpos:`: the settings used, which extraction path ran, and each image's size and dither method. `DEBUG` lines need `sudo cupsctl --debug-logging` (turn it off afterwards with `--no-debug-logging`). Then run `sudo tail -f /var/log/cups/error_log`.

`cupsfilter` isn't useful for testing here: cups-filters 2.0 converts everything to PostScript and never calls this filter.

## License

MIT
