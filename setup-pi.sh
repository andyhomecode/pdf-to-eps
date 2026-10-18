#!/usr/bin/env bash
# setup-pi.sh — make a Raspberry Pi the print server for the Citizen CD-S500A:
# CUPS, the pdf2escpos.py filter and a receipt-citizen queue on the USB
# printer, shared over AirPrint. The queue prints text only, with bold in red.
#
#   sudo ./setup-pi.sh                 # find the Citizen on USB and set it all up
#   sudo ./setup-pi.sh --uri URI       # use this device URI instead (from lpinfo -v)
#
# Running it again updates the filter and PPD, keeping the queue's defaults
# (the same as sudo ./install.sh --queue receipt-citizen). It also moves a
# queue still on a usb:// URI to the kernel's /dev/usb/lp device.
#
# The queue prints to parallel:/dev/usb/lpN, not usb://CBM/CD-S500. CUPS's
# usb backend hangs writing to this printer on the Pi (even with the unidir
# quirk) and leaves it unable to take data until it's switched off and on.
# Writing through the kernel's usblp driver works.

set -euo pipefail

QUEUE=receipt-citizen
PPD=ppd/receipt-citizen.ppd
FILTER_DIR=/usr/lib/cups/filter
URI=""

cd "$(dirname "$0")"

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --uri)     URI="$2"; shift 2 ;;
        -h|--help) usage ;;
        *)         echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo." >&2
    exit 1
fi

# Text only, so no python3-pil: the filter prints text without it
apt-get update
apt-get install -y cups avahi-daemon python3 poppler-utils
systemctl enable --now cups avahi-daemon   # avahi advertises the queue to iPhones and Macs

# Share printers, and allow the CUPS web page (http://<pi>:631) from the LAN.
# The user who ran sudo can then change printer defaults there.
cupsctl --share-printers --remote-admin
if [ -n "${SUDO_USER:-}" ]; then
    usermod -aG lpadmin "$SUDO_USER"
fi

# The Citizen's usblp device, found by its USB vendor ID (Citizen Systems)
citizen_lp() {
    local dev
    for dev in /sys/class/usbmisc/lp*; do
        [ -e "$dev" ] || continue
        if [ "$(cat "$dev/device/../idVendor" 2>/dev/null)" = 2730 ]; then
            echo "parallel:/dev/usb/$(basename "$dev")"
            return
        fi
    done
}

if lpstat -p "$QUEUE" >/dev/null 2>&1; then
    ./install.sh --queue "$QUEUE"
    if lpstat -v "$QUEUE" | grep -q ' usb://' && [ -n "$(citizen_lp)" ]; then
        lpadmin -p "$QUEUE" -v "$(citizen_lp)"
        echo "Moved $QUEUE to $(citizen_lp)"
    fi
    exit 0
fi

# First time. The filter goes in first: cupstestppd checks the PPD's filter exists.
python3 -m py_compile pdf2escpos.py
install -m 755 -o root -g root pdf2escpos.py "$FILTER_DIR/pdf2escpos.py"
cupstestppd -W translations "$PPD" >/dev/null || {
    cupstestppd -W translations "$PPD" >&2 || true
    exit 1
}

if [ -z "$URI" ]; then
    URI=$(citizen_lp)
fi
if [ -z "$URI" ]; then
    echo "No Citizen printer found on USB (no /dev/usb/lp* with vendor 2730). Is it on and plugged in? USB printers seen:" >&2
    ls -l /dev/usb/lp* >&2 || true
    lpinfo --include-schemes usb -v >&2 || true
    echo "Pick its device and run: sudo ./setup-pi.sh --uri 'parallel:/dev/usb/lp0'" >&2
    echo "(If it's missing, it may show up as a serial port: ls /dev/ttyACM* /dev/ttyUSB*" >&2
    echo " and then use --uri 'serial:/dev/ttyACM0?baud=9600'.)" >&2
    exit 1
fi

# Letter paper, so phones lay out a normal page and the filter reflows it to the roll
lpadmin -p "$QUEUE" -E -v "$URI" -P "$PPD" -D "Citizen Receipt" \
    -o printer-is-shared=true -o PageSize=Letter -o PageRegion=Letter
echo "Created queue $QUEUE on $URI"
lpstat -p "$QUEUE"

cat <<EOF

Next:
  Test page (columns, bold, red, code pages, cut):
    python3 tools/test_page.py --profile citizen-cd-s500a | lp -d $QUEUE -o raw
  A document:
    lp -d $QUEUE tests/fixtures/receipt.pdf
  Defaults (columns, character set, bold in red):
    http://$(hostname).local:631/printers/$QUEUE  (Administration -> Set Default Options)
EOF
