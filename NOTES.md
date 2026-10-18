# Notes: printers, setup and plans

## Printers

| Printer | Type | Connection | Queue | Status |
|---|---|---|---|---|
| Epson TM-T20II | Thermal receipt, 80mm, 203 dpi, autocutter | Ethernet, `socket://192.168.1.16:9100` (the "receipt" box on the LAN) | `thermal-receipt` (80mm, as drawn) and `thermal-receipt-text` (Letter, reflowed) | In use, shared over AirPrint |
| Citizen CD-S500A | 9-pin impact receipt, ESC/POS, USB-B, 76mm paper (40 columns), black/red ribbon (IR-31) | USB-B into a Raspberry Pi 3 B running CUPS | `receipt-citizen` (Letter/A4, reflowed, text only, bold in red) | Phase 2: set up, not yet checked on the printer |
| OKI ML420 | 9-pin dot matrix, Epson FX / IBM emulation (ESC/P, not ESC/POS), USB-B | Not connected yet | its own queue (planned) | Phase 3 |

The Epson queues run on the ThinkCentre and the Citizen's on the Pi (`/usr/lib/cups/filter/pdf2escpos.py`, PPDs in `ppd/`). All and are shared over AirPrint, so iPhones and Macs print to them directly. How the server side is set up, and how to rebuild it, is in the ThinkCentre reference doc (`thinkcentre-reference.md` in Dropbox, section "Receipt Printer").

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

Decided 2026-10-17: the **Raspberry Pi 3 B is the Citizen's print server**, running its own CUPS, this filter and avahi, with the printer on its USB. `setup-pi.sh` sets it up. The printer is **text only** (no photos, drawings or images in PDFs; Andy wants it that way, and it means the `ESC *` image path never needs writing) and **bold prints red** instead of bold (`BoldInRed`, default on). Headings and red text in the PDF print red too.

- The PPD has Letter and A4 paper, like `thermal-receipt-text`, so phones lay out a normal page and the filter reflows it. It says it's a color device, so iOS keeps red text red in the PDF it sends.
- Column count (40), the code page numbers, the `GS V 1` cut, `ESC r` red, and red switching mid-line all come from the CD-S500 family's spec sheets and ESC/POS, not from the printer.

Still to do:
1. Run `sudo ./setup-pi.sh` on the Pi with the printer plugged in. If no `usb://` URI shows up, the printer may present a serial port instead (`/dev/ttyACM0`).
2. Print `tools/test_page.py --profile citizen-cd-s500a` raw, and fix the profile from what prints: where the ruler wraps (columns), red (whole line and mid-line), double sizes, which code pages print `é £ €` right, and the cut (fall back to a feed if it has no autocutter). The cutter sits further from the head than on the Epson, so `cut_feed_lines` may need raising.
3. Print from the iPhone and the Mac, then update this file and the reference doc.
4. Later: the OKI can go on the same Pi as a second queue.

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
