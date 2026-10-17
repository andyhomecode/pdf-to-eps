# Notes: printers, setup and plans

## Printers

| Printer | Type | Connection | Queue | Status |
|---|---|---|---|---|
| Epson TM-T20II | Thermal receipt, 80mm, 203 dpi, autocutter | Ethernet, `socket://192.168.1.16:9100` (the "receipt" box on the LAN) | `thermal-receipt` (80mm, as drawn) and `thermal-receipt-text` (Letter, reflowed) | In use, shared over AirPrint |
| Citizen CD-S500A | 9-pin impact receipt, ESC/POS, USB-B, probably 76mm paper, maybe a red/black ribbon | Not connected yet | `receipt-citizen` (planned) | Phase 2 |
| OKI ML420 | 9-pin dot matrix, Epson FX / IBM emulation (ESC/P, not ESC/POS), USB-B | Not connected yet | its own queue (planned) | Phase 3 |

All queues run on the ThinkCentre (`/usr/lib/cups/filter/pdf2escpos.py`, PPDs in `ppd/`) and are shared over AirPrint, so iPhones and Macs print to them directly. How the server side is set up, and how to rebuild it, is in the ThinkCentre reference doc (`thinkcentre-reference.md` in Dropbox, section "Receipt Printer").

## How a job reaches the printer

- **PDF from the iPhone or a Mac** (web pages, email): iOS and macOS lay the content out on the queue's 80mm page, so the PDF's pages are exactly the paper's width. `pdf2escpos.py` prints those pages as drawn, matching the print preview, and lets Apple decide the layout. Chosen on 2026-10-17 after per-PDF reflow fixes kept piling up. The cost is paper: a long web page in iOS's large font can run over a metre and a half (175 cm for one NYC DEP page, against 58 cm reflowed). `PrintMode=Text` reflows instead.
- **Other PDFs** (A4 or Letter documents, attachments): laid out as printer text, reflowed to 48 columns.
- **JPEG/PNG** (photos from the phone): the iPhone sends `image/jpeg` on the borderless 80x297mm page. CUPS's own image filter would rotate and crop the photo to fill that strip (seen 2026-10-17), so the PPD's `*cupsFilter` lines route images straight to `pdf2escpos.py`, which prints the whole photo at the paper width.
- **Raw** (`lp -o raw`): goes straight to the printer.

## Changing the defaults phones use

AirPrint doesn't show the custom menus (Columns, Character Set, Print Mode, Dithering, Print Job Title). Phone and Mac jobs use the queue's defaults. Change those on http://localhost:631/printers/thermal-receipt (Administration → Set Default Options), or with `sudo lpadmin -p thermal-receipt -o Dither-default=Atkinson`.

## Tuning

- **Image darkness:** `image_gamma` in the profile (0.8 on the Epson). Lower values lighten midtones. Impact printers spread more, so they'll need a lower value.
- **Auto dither:** images with at least 90% of pixels near black or white are thresholded. Others get Atkinson. QR fixture: 94%, photo: 51%, text pages: 97-99%.
- **QR codes in emails** stay scannable: on 2026-10-17 a Gmail ticket's QR printed at 441 dots (about 13 dots per module), and ZXing decoded the exact printed bits, even at half size.
- **Embedded images:** the size rules are `FULL_WIDTH_FRACTION`, `MIN_IMAGE_FRACTION` and `MIN_IMAGE_PT` at the top of the Layout section.
- **Layout thresholds** (top of the Layout section in `pdf2escpos.py`): heading size ratios, the 0.75× cutoff for dropping small diagram text, and the 8% page margin zone checked for headers and footers.
- **As-drawn pages:** `TEXT_THRESHOLD` (170) decides what's paper and what's ink. It's above middle gray so light-gray text survives. Photos in the page (its raster images) are dithered separately.
- **Web pages reflowed with `PrintMode=Text`:** lines spanning 60% or more of the page's text width (`PROSE_WIDTH_SHARE`) count as running text, and a paragraph split by a page break is joined back up.
- **Checking a change:** put real documents in `tests/private/` (git-ignored) and run `python3 tools/corpus.py --ref main` to see which of them print differently.

## Phase 2: Citizen CD-S500A

Connection: **USB-B straight into the ThinkCentre** if it can sit in the shoe room (URI from `lpinfo -v`, `usb://Citizen/...`). Otherwise use a **Raspberry Pi running `p910nd`** (raw port 9100, one port per printer, so the same Pi can drive the OKI too) with `socket://<pi>:9100`. The filter works the same either way.

Checklist:
1. Add a `citizen-cd-s500a` profile: impact, about 40 columns (to verify), `GS V` cut, `ESC r 1` for red, images as `ESC *` 8-dot bands with `ESC 3` line spacing, and a lower `image_gamma`. Images currently only support `GS v 0`, so the `ESC *` path has to be written.
2. Create `ppd/citizen-cd-s500a.ppd` with `EscposProfile=citizen-cd-s500a`, then a `receipt-citizen` queue, shared over AirPrint.
3. Add a calibration print (`PrintMode=Calibrate`): a column ruler for each font, a code page sample, bold, double-height and red samples, a dot-width ruler, the same photo with all three dither methods, then a cut.
4. Fix the profile from what prints: column counts, dots, image density and band alignment, the cut command (some units have no autocutter, so fall back to a feed), and red.
5. Print from the iPhone and the Mac, then update this file and the reference doc.

## Phase 3: OKI ML420

**Why:** today the OKI can only print from Windows, through OKI's driver, which rasterizes PDFs: slow, and low quality compared with native text. Nothing prints to it from a Mac or iPhone. With this filter it would print text as fast native text over AirPrint, and rasterize only image pages.

Plan:
- An `escp` command set in the renderer: 80 or 136 columns depending on pitch, a form feed per page instead of a cut, `ESC E` bold, `ESC W` double width, `ESC *` 8-pin graphics for image pages, and the ESC/P code page command.
- Its own PPD and queue, connected by USB-B to the ThinkCentre or the same Pi as the Citizen.

## CUPS and PPDs

`lpadmin -P` warns "Printer drivers are deprecated and will stop working in a future version of CUPS". CUPS 2.4 (Ubuntu 24.04) still supports PPD queues fully. CUPS 3 plans to drop them for "printer applications" (PAPPL), small services that appear on the network as driverless IPP printers. When an Ubuntu release with CUPS 3 comes, the filter's logic can move into a printer application that hands it the same PDF, JPEG and PNG input. Only the PPD and the queue setup would need replacing.

**Fallback if CUPS stops running this filter: [LPrint](https://github.com/michaelrsweet/lprint).** It's a PAPPL printer application by Michael Sweet, CUPS's author. Since v1.4.0 (June 2026) it has an ESC/POS driver for Epson TM-series printers, and it appears as a driverless IPP Everywhere printer to iPhones, Macs, Android and Windows. Looked at on 2026-10-17 and not adopted, because:
- It takes only raster, PNG or raw data, not PDF, so there's no text reflow. The `thermal-receipt-text` queue has no equivalent.
- What it would replace is the as-drawn queue (`thermal-receipt`), since the iPhone rasterizes the page itself.
- Untested: how its dithering treats text and QR codes, whether it trims blank paper at page ends, and whether iOS crops photos to fill the page as CUPS's image filter did.
- Its ESC/POS driver was new, and the README warned that master had known issues.

If a CUPS upgrade blocks PPD queues before this filter is ported to a printer application, the quickest way to keep printing from phones is LPrint pointed at `socket://192.168.1.16:9100`. Compare its prints with this filter's on the corpus samples (Fujikina ticket, Citizens page, a photo) before switching. The text queue would need this filter ported to PAPPL, or a CUPS raw queue fed by `pdf2escpos.py` from a script.

## Ideas not done yet

- Landscape photos print full width but short (a 4:3 photo is about 7 x 5 cm). They could be turned sideways to print larger along the paper.
- Vector drawings (SVG logos in emails, charts) aren't printed on pages that have text. `pdftohtml` only reports raster images; finding drawings means rendering the page and looking for drawn areas that aren't text.
- The CUPS Scaling option (Auto, Fit, Fill, None) is ignored.
- A hyphen at the end of a line is always treated as a word broken by the line: `health-` / `related` prints as `healthrelated`. Position alone can't tell it from `re-` / `ceptors`.
- Email headers (From, Reply-To, To) sometimes run together into one paragraph.
- Separate short lines can join into one paragraph when each item fills its line, as with the meeting dates in a 2026-10-17 village notice. Position alone can't tell these from wrapped text.
