# Notes: printers, setup and plans

## Printers

| Printer | Type | Connection | Queue | Status |
|---|---|---|---|---|
| Epson TM-T20II | Thermal receipt, 80mm, 203 dpi, autocutter | Ethernet, `socket://192.168.1.16:9100` (the "receipt" box on the LAN) | `thermal-receipt` (80mm, as drawn) and `thermal-receipt-text` (Letter, reflowed) | In use, shared over AirPrint |
| Citizen CD-S500A | 9-pin impact receipt, ESC/POS, USB-B, 76mm paper (40 columns), black/red ribbon (IR-31), no cutter | USB-B into a Raspberry Pi 3 B running CUPS (`printserver-citizen`) | `receipt-citizen` (Letter/A4, reflowed, text only, bold in red) | Phase 2: queue set up on the Pi, test page checked |
| OKI ML420 | 9-pin dot matrix, Epson FX / IBM emulation (ESC/P, not ESC/POS), USB-B | Not connected yet | its own queue (planned) | Phase 3 |

The Epson queues run on the ThinkCentre and the Citizen's on the Pi `printserver-citizen` (`/usr/lib/cups/filter/pdf2escpos.py`, PPDs in `ppd/`). All are shared over AirPrint, so iPhones and Macs print to them directly. How the server side is set up, and how to rebuild it, is in the ThinkCentre reference doc (`thinkcentre-reference.md` in Dropbox, section "Receipt Printer").

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
- It has no cutter, so jobs end with a feed to tear off, and the profile sends no cut command. The feed is the profile's `cut_feed_lines`: 7 lines of Font B brings the last line past the tear bar (6 fell one line short, 2026-10-18).
- Test page results (2026-10-18):
  - Columns: the printer's default font and Font B (`ESC M 1`) fit 40, Font A (`ESC M 0`) only 33. The profile selects Font B; it used to select Font A, which would have wrapped every 40-column line. `ESC !` (text size) also sets the font in bit 0, so the filter keeps the profile's font in it; a plain `ESC ! 0` after a heading put the first receipt back in Font A.
  - Bold, red (whole line and mid-line), underline, double height, double width and double size all print.
  - Code pages: cp437 (0), cp858 (19) and latin-1 (16) all print `é ü ñ £ ½ ¿ ¡` right. None prints `€`: cp437 has none, and cp858 and latin-1 print a stray loopy glyph in its place. The profile's `no_glyph` makes `€` print as `EUR` on every code page.
  - No cutter (see above).

The Pi so far (2026-10-18):
- Hostname `printserver-citizen`, reached as `printserver-citizen.local` over mDNS (192.168.1.29 on 2026-10-18). Its CUPS page is http://printserver-citizen.local:631.
- SSH as `andy@printserver-citizen.local`, public-key login only, from `andy-thinkpad`'s key.
- git is installed, with the Pi's own SSH key added to GitHub, and this repo is cloned on it.
- The printer shows up as a USB printer: `lsusb` gives `2730:1004 Citizen PPU-700` (interface board IF-USB-P03, interface class 7 Printer) and `/dev/usb/lp0` exists. CUPS lists it as `usb://CBM/CD-S500` (CBM is Citizen Business Machines), not a serial port.
- The first `sudo ./setup-pi.sh` installed CUPS, avahi and poppler but didn't find the printer, because it only looked for `usb://Citizen...`. It now accepts `usb://CBM/...` too. Rerun with `--uri 'usb://CBM/CD-S500'`, it created `receipt-citizen`, and the test page printed.

To update it after a change: `ssh -t andy@printserver-citizen.local`, `cd` into the clone, `git pull`, then `sudo ./setup-pi.sh` (it updates the filter and PPD and keeps the queue's defaults).

Still to do:
1. ~~Run `setup-pi.sh` and create `receipt-citizen`~~ (done 2026-10-18).
2. ~~Check the test page and fix the profile~~ (done 2026-10-18, results above). The first receipt sent straight to `/dev/usb/lp0` printed right: 40 columns, red heading and total.
3. Print through CUPS: on 2026-10-18 job `receipt-citizen-2` sat at "Sending data to printer" and printed nothing, while the same bytes written to `/dev/usb/lp0` printed. Check a job goes through with the fixed filter; if it still hangs, try a USB quirk for `2730:1004` (e.g. `unidir`) in `/usr/share/cups/usb/`.
4. Print from the iPhone and the Mac, then update this file and the reference doc.
5. Later: the OKI can go on the same Pi as a second queue.

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
