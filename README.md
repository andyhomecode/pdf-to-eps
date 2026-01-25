# PDF to ESC/POS CUPS Filter

A CUPS filter that converts PDF documents to ESC/POS format for thermal receipt printers.

## Overview

`pdf2escpos.py` is a CUPS filter that:
- Extracts text from PDF files using `pdftotext`
- Formats text for thermal receipt printers (48-column default)
- Generates ESC/POS commands for proper printing
- Supports text alignment, bold, underline formatting
- Handles margins, headers, footers, and paper cutting

## Features

- **Text Extraction**: Uses `pdftotext` for reliable PDF text extraction
- **Text Wrapping**: Automatic line wrapping for receipt widths
- **Formatting Support**: Bold, underline, left/center/right alignment
- **Configurable**: Environment variables for customization
- **Error Handling**: Graceful fallback for problematic PDFs
- **Memory Safe**: Proper cleanup of temporary files
- **Security**: Input validation and bounds checking

## Requirements

### System Dependencies
```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils python3

# CentOS/RHEL/Fedora
sudo yum install poppler-utils python3
# or
sudo dnf install poppler-utils python3
```

### Python Version
- Python 3.6 or higher
- Uses only standard library modules

## Installation

### 1. Install System Dependencies
```bash
sudo apt-get install poppler-utils python3
sudo apt install avahi-daemon avahi-utils
```

### 2. Copy Filter to CUPS
```bash
# Copy the filter to CUPS filter directory
sudo cp pdf2escpos.py /usr/lib/cups/filter/
sudo chmod 755 /usr/lib/cups/filter/pdf2escpos.py

# Verify installation
ls -la /usr/lib/cups/filter/pdf2escpos.py
```

### 3. Create PPD File
Create `/usr/share/cups/model/thermal-receipt.ppd`:

```ppd
*PPD-Adobe: "4.3"
*FormatVersion: "4.3"
*FileVersion: "1.0"
*LanguageVersion: English
*LanguageEncoding: ISOLatin1
*PCFileName: "thermal.ppd"
*Product: "(Thermal Receipt Printer)"
*Manufacturer: "Generic"
*ModelName: "Thermal Receipt Printer"
*ShortNickName: "Thermal Receipt"
*NickName: "Thermal Receipt Printer"
*PSVersion: "(3010.000) 0"
*LanguageLevel: "3"
*ColorDevice: False
*DefaultColorSpace: Gray
*FileSystem: False
*Throughput: "1"
*LandscapeOrientation: Plus90
*TTRasterizer: Type42

*OpenUI *PageSize/Page Size: PickOne
*DefaultPageSize: Receipt80mm
*PageSize Receipt80mm/80mm Receipt: "<</PageSize[226.77 841.89]/ImagingBBox null>>setpagedevice"
*PageSize Receipt58mm/58mm Receipt: "<</PageSize[164.41 841.89]/ImagingBBox null>>setpagedevice"
*CloseUI: *PageSize

*OpenUI *PageRegion: PickOne
*DefaultPageRegion: Receipt80mm
*PageRegion Receipt80mm/80mm Receipt: "<</PageSize[226.77 841.89]/ImagingBBox null>>setpagedevice"
*PageRegion Receipt58mm/58mm Receipt: "<</PageSize[164.41 841.89]/ImagingBBox null>>setpagedevice"
*CloseUI: *PageRegion

*DefaultImageableArea: Receipt80mm
*ImageableArea Receipt80mm/80mm Receipt: "0.00 0.00 226.77 841.89"
*ImageableArea Receipt58mm/58mm Receipt: "0.00 0.00 164.41 841.89"

*DefaultPaperDimension: Receipt80mm
*PaperDimension Receipt80mm/80mm Receipt: "226.77 841.89"
*PaperDimension Receipt58mm/58mm Receipt: "164.41 841.89"

*OpenUI *EscposCols/Columns: PickOne
*DefaultEscposCols: 48
*EscposCols 32/32 columns: ""
*EscposCols 42/42 columns: ""
*EscposCols 48/48 columns: ""
*CloseUI: *EscposCols

*OpenUI *EscposCodepage/Character Set: PickOne
*DefaultEscposCodepage: cp437
*EscposCodepage cp437/CP437 (US): ""
*EscposCodepage cp858/CP858 (Western Europe): ""
*EscposCodepage latin-1/Latin-1: ""
*CloseUI: *EscposCodepage

*cupsFilter: "application/pdf 0 pdf2escpos.py"
*cupsManualCopies: True
```

### 4. Add Printer
```bash
# Add a new printer using the PPD
sudo lpadmin -p thermal-receipt -E -v file:/dev/null -P /usr/share/cups/model/thermal-receipt.ppd

# Or for a real printer (USB example)
sudo lpadmin -p thermal-receipt -E -v usb://EPSON/TM-T20II -P /usr/share/cups/model/thermal-receipt.ppd

# Or for network printer -- that's what I'm using for my Epson, others untested
sudo lpadmin -p thermal-receipt -E -v socket://192.168.1.16:9100 -P /usr/share/cups/model/thermal-receipt.ppd
```

### 5. Restart CUPS
```bash

sudo cupsctl --share-printers --remote-any --remote-admin
sudo systemctl restart cups
ss -lntp | grep 631
sudo systemctl enable --now avahi-daemon
avahi-browse -a | grep Printer

```

## Configuration

### Environment Variables

The filter can be configured using environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ESCPOS_COLS` | `48` | Text columns (1-1000) |
| `ESCPOS_CODEPAGE` | `cp437` | Character encoding |
| `ESCPOS_LEFT` | `0` | Left margin spaces (0-50) |
| `ESCPOS_RIGHT` | `0` | Right margin spaces (0-50) |
| `ESCPOS_HEADER` | `""` | Header text (max 200 chars) |
| `ESCPOS_FOOTER` | `""` | Footer text (max 200 chars) |
| `ESCPOS_CUT_FEED_LINES` | `6` | Line feeds before cutting (0-20) |

### CUPS Backend Configuration

For persistent configuration, modify the CUPS backend or create a wrapper script:

```bash
#!/bin/bash
# /usr/lib/cups/filter/pdf2escpos-wrapper.py

export ESCPOS_COLS=42
export ESCPOS_HEADER="STORE RECEIPT"
export ESCPOS_FOOTER="Thank you for your business!"

exec /usr/lib/cups/filter/pdf2escpos.py "$@"
```

## Usage

### Command Line Testing
```bash
# Test with file
python3 pdf2escpos.py 1234 user "Test Document" 1 "" document.pdf > output.escpos

# Test with stdin
cat document.pdf | python3 pdf2escpos.py 1234 user "Test" 1 "" - > output.escpos

# Test with custom settings
ESCPOS_COLS=32 ESCPOS_HEADER="RECEIPT" python3 pdf2escpos.py 1234 user "Test" 1 "" document.pdf > output.escpos
```

### Printing from Applications
Once configured, any application can print PDFs to the thermal printer:

```bash
# Command line
lp -d thermal-receipt document.pdf

# From browser or other applications
# Select "Thermal Receipt Printer" as the destination
```

## Text Formatting

The filter supports simple formatting directives within the PDF text:

### Alignment
- `[LEFT]` - Left align text (default)
- `[CENTER]` - Center align text  
- `[RIGHT]` - Right align text

### Text Style
- `[B]text[/B]` - Bold text
- `[U]text[/U]` - Underlined text

### Special Commands
- `[CUT]` - Insert paper cut command

### Example PDF Content
```
[CENTER][B]STORE RECEIPT[/B]

[LEFT]Date: 2024-09-22
Time: 14:30:22

[CENTER]Items Purchased

[LEFT]Item 1 .............. $10.00
Item 2 .............. $15.50
Tax .................. $2.55

[CENTER][B]Total: $28.05[/B]

[CUT]
```

## Troubleshooting

### Common Issues

1. **Filter not found**
   ```bash
   # Check filter permissions
   ls -la /usr/lib/cups/filter/pdf2escpos.py
   # Should be executable (755)
   ```

2. **pdftotext command not found**
   ```bash
   # Install poppler-utils
   sudo apt-get install poppler-utils
   ```

3. **No output or garbled text**
   ```bash
   # Test filter directly
   python3 pdf2escpos.py 1234 user "Test" 1 "" test.pdf | od -c
   # Should show ESC/POS commands
   ```

4. **Wrong character encoding**
   - Set `ESCPOS_CODEPAGE` to match your printer
   - Common options: `cp437`, `cp858`, `latin-1`

### Debugging

Enable debug output:
```bash
# Add debug prints to the script
# Check CUPS error log
sudo tail -f /var/log/cups/error_log

# Test individual components
pdftotext -layout -nopgbrk test.pdf -
```

### Log Files
- CUPS error log: `/var/log/cups/error_log`
- CUPS access log: `/var/log/cups/access_log`

## Printer Compatibility

### Tested Printers
- Epson TM-T20II/III
- Star TSP100 series
- Generic ESC/POS thermal printers

### ESC/POS Commands Used
- `ESC @` - Initialize printer
- `ESC M` - Select font
- `ESC a` - Text alignment
- `ESC E` - Bold on/off
- `ESC -` - Underline on/off
- `ESC m` - Paper cut (0x1B 0x6D)

## Security Considerations

- Input validation on all environment variables
- File path sanitization to prevent directory traversal
- Bounds checking on configuration values
- Safe temporary file handling
- Proper subprocess execution

## License

This project is released under the MIT License.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with proper error handling
4. Add tests for new functionality
5. Submit a pull request

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review CUPS error logs
3. Test the filter directly from command line
