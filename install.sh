#!/usr/bin/env bash
# install.sh — install pdf2escpos.py and a queue's PPD on this machine.
#
#   sudo ./install.sh                      # filter + ppd/thermal-receipt.ppd -> queue thermal-receipt
#   sudo ./install.sh --queue receipt-citizen
#   sudo ./install.sh --filter-only        # leave the PPD alone
#   sudo ./install.sh --test some.pdf      # also send a test print afterwards
#   sudo ./install.sh --rollback           # put back the previous filter and PPD
#
# Each install keeps the previous filter as pdf2escpos.py.bak and the previous
# PPD as /etc/cups/ppd/<queue>.ppd.bak, so --rollback undoes one install.

set -euo pipefail

FILTER_DIR=/usr/lib/cups/filter
FILTER=pdf2escpos.py
PPD_DIR=/etc/cups/ppd
QUEUE=thermal-receipt
PPD=""
FILTER_ONLY=0
ROLLBACK=0
TEST_FILE=""

cd "$(dirname "$0")"

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --queue)       QUEUE="$2"; shift 2 ;;
        --ppd)         PPD="$2"; shift 2 ;;
        --filter-only) FILTER_ONLY=1; shift ;;
        --test)        TEST_FILE="$2"; shift 2 ;;
        --rollback)    ROLLBACK=1; shift ;;
        -h|--help)     usage ;;
        *)             echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

[ -n "$PPD" ] || PPD="ppd/$QUEUE.ppd"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo." >&2
    exit 1
fi

if ! lpstat -p "$QUEUE" >/dev/null 2>&1; then
    echo "No CUPS queue named '$QUEUE'." >&2
    exit 1
fi

if [ "$ROLLBACK" -eq 1 ]; then
    if [ -f "$FILTER_DIR/$FILTER.bak" ]; then
        install -m 755 -o root -g root "$FILTER_DIR/$FILTER.bak" "$FILTER_DIR/$FILTER"
        echo "Restored $FILTER_DIR/$FILTER from .bak"
    else
        echo "No $FILTER_DIR/$FILTER.bak to restore." >&2
    fi
    if [ "$FILTER_ONLY" -eq 0 ] && [ -f "$PPD_DIR/$QUEUE.ppd.bak" ]; then
        lpadmin -p "$QUEUE" -P "$PPD_DIR/$QUEUE.ppd.bak"
        echo "Restored $QUEUE PPD from $PPD_DIR/$QUEUE.ppd.bak"
    fi
    exit 0
fi

# Don't install a filter that doesn't even compile
python3 -m py_compile "$FILTER"

if [ -f "$FILTER_DIR/$FILTER" ]; then
    cp -p "$FILTER_DIR/$FILTER" "$FILTER_DIR/$FILTER.bak"
fi
install -m 755 -o root -g root "$FILTER" "$FILTER_DIR/$FILTER"
echo "Installed $FILTER_DIR/$FILTER (previous kept as $FILTER.bak)"

if [ "$FILTER_ONLY" -eq 0 ]; then
    if [ ! -f "$PPD" ]; then
        echo "No $PPD; use --ppd FILE or --filter-only." >&2
        exit 1
    fi
    cupstestppd -W translations "$PPD" >/dev/null || {
        echo "cupstestppd failed for $PPD:" >&2
        cupstestppd -W translations "$PPD" >&2 || true
        exit 1
    }
    cp -p "$PPD_DIR/$QUEUE.ppd" "$PPD_DIR/$QUEUE.ppd.bak"
    # CUPS carries the queue's current default choices over to the new PPD
    lpadmin -p "$QUEUE" -P "$PPD"
    echo "Installed $PPD for queue $QUEUE (previous kept as $PPD_DIR/$QUEUE.ppd.bak)"
fi

lpstat -p "$QUEUE"
lpoptions -p "$QUEUE" -l

if [ -n "$TEST_FILE" ]; then
    lp -d "$QUEUE" -t "install.sh test" "$TEST_FILE"
fi
