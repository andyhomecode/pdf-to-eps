# pdf2escpos

A CUPS filter that prints PDFs, photos and images on an ESC/POS receipt printer, so an Epson TM-T20II shared over AirPrint works from an iPhone or Mac like any other printer.

Instead of rasterizing every page, it reads the PDF's text, layout and fonts and prints them as native printer text: sharp, fast and laid out for a 48-column roll. Pages without text and photos print as dithered images.

It runs on the ThinkCentre server as the filter for the `thermal-receipt` queue. `NOTES.md` covers the printers, how they're connected and what's planned next.

## What it does

**Text** (from `pdftohtml -xml`, falling back to `pdftotext -layout`):
- Paragraphs are rejoined and rewrapped to the paper width, and words hyphenated at line ends are mended.
- Bullet and numbered items wrap with a hanging indent. Word's Symbol-font bullets print as `*`.
- Label/value rows, table rows and dot-leader prices (`Latte ...... $4.50`) print with the value right-aligned. Lines of `-`, `_`, `=` or `*` print as one full-width rule.
- Short-line columns, such as an address, keep their line breaks.
- Headings print double height (1.4× the body size) or double size (2×). Bold text prints bold. Red text prints red on printers that have it, otherwise bold. Centered and right-aligned lines keep their alignment.
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
| `PageSize` | Receipt80mm, Receipt58mm (58mm caps columns at 35 and images at 416 dots) | Receipt80mm |
| `PrintMode` | Auto (pages without text print as images), Text, Image | Auto |
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
sudo cupsctl --share-printers
sudo systemctl enable --now avahi-daemon   # AirPrint discovery

# Install or update the filter and PPD
sudo ./install.sh                  # filter + ppd/thermal-receipt.ppd
sudo ./install.sh --filter-only    # filter only
sudo ./install.sh --test tests/fixtures/receipt.pdf   # and print a test page
sudo ./install.sh --rollback       # back to the previous filter and PPD
```

`install.sh` won't install a filter that doesn't compile or a PPD that fails `cupstestppd`. Each install keeps the previous filter as `/usr/lib/cups/filter/pdf2escpos.py.bak` and the previous PPD as `/etc/cups/ppd/<queue>.ppd.bak`. It needs a real terminal for `sudo`.

The PPD sends `application/pdf`, `image/jpeg` and `image/png` straight to the filter. Images have to skip CUPS's own image filter, which would crop a photo to fill the long receipt page.

## Testing

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
