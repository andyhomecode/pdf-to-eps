#!/usr/bin/env bash
# install.sh — install pdf2escpos.py, and the PPD on each receipt queue.
#
#   sudo ./install.sh                      # filter + ppd/thermal-receipt.ppd on both receipt queues
#   sudo ./install.sh --queue receipt-citizen --ppd ppd/citizen-cd-s500a.ppd
#   sudo ./install.sh --filter-only        # leave the PPDs alone
#   sudo ./install.sh --test some.pdf      # also send a test print (to the first queue)
#   sudo ./install.sh --rollback           # put back the previous filter and PPDs
#
# The two receipt queues share one printer and one PPD: thermal-receipt
# defaults to 80mm paper (pages print as drawn) and thermal-receipt-text to
# Letter (pages are reflowed as text). A queue that doesn't exist yet is
# skipped. CUPS keeps each queue's own defaults when its PPD is replaced.
#
# Each install keeps the previous filter as pdf2escpos.py.bak and each queue's
# previous PPD as /etc/cups/ppd/<queue>.ppd.bak, so --rollback undoes one install.

set -euo pipefail

FILTER_DIR=/usr/lib/cups/filter
FILTER=pdf2escpos.py
PPD_DIR=/etc/cups/ppd
DEFAULT_QUEUES=(thermal-receipt thermal-receipt-text)
QUEUES=()
PPD=ppd/thermal-receipt.ppd
FILTER_ONLY=0
ROLLBACK=0
TEST_FILE=""

cd "$(dirname "$0")"

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --queue)       QUEUES+=("$2"); shift 2 ;;
        --ppd)         PPD="$2"; shift 2 ;;
        --filter-only) FILTER_ONLY=1; shift ;;
        --test)        TEST_FILE="$2"; shift 2 ;;
        --rollback)    ROLLBACK=1; shift ;;
        -h|--help)     usage ;;
        *)             echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo." >&2
    exit 1
fi

# Queues named with --queue must exist; of the defaults, use the ones that do
if [ "${#QUEUES[@]}" -gt 0 ]; then
    for q in "${QUEUES[@]}"; do
        lpstat -p "$q" >/dev/null 2>&1 || { echo "No CUPS queue named '$q'." >&2; exit 1; }
    done
else
    for q in "${DEFAULT_QUEUES[@]}"; do
        if lpstat -p "$q" >/dev/null 2>&1; then
            QUEUES+=("$q")
        else
            echo "No queue '$q' yet; skipping it."
        fi
    done
    [ "${#QUEUES[@]}" -gt 0 ] || { echo "None of ${DEFAULT_QUEUES[*]} exist." >&2; exit 1; }
fi

if [ "$ROLLBACK" -eq 1 ]; then
    if [ -f "$FILTER_DIR/$FILTER.bak" ]; then
        install -m 755 -o root -g root "$FILTER_DIR/$FILTER.bak" "$FILTER_DIR/$FILTER"
        echo "Restored $FILTER_DIR/$FILTER from .bak"
    else
        echo "No $FILTER_DIR/$FILTER.bak to restore." >&2
    fi
    if [ "$FILTER_ONLY" -eq 0 ]; then
        for q in "${QUEUES[@]}"; do
            if [ -f "$PPD_DIR/$q.ppd.bak" ]; then
                lpadmin -p "$q" -P "$PPD_DIR/$q.ppd.bak"
                echo "Restored $q PPD from $PPD_DIR/$q.ppd.bak"
            fi
        done
    fi
    exit 0
fi

# Don't install a filter that doesn't even compile, or a PPD CUPS rejects
python3 -m py_compile "$FILTER"
if [ "$FILTER_ONLY" -eq 0 ]; then
    [ -f "$PPD" ] || { echo "No $PPD; use --ppd FILE or --filter-only." >&2; exit 1; }
    cupstestppd -W translations "$PPD" >/dev/null || {
        echo "cupstestppd failed for $PPD:" >&2
        cupstestppd -W translations "$PPD" >&2 || true
        exit 1
    }
fi

if [ -f "$FILTER_DIR/$FILTER" ]; then
    cp -p "$FILTER_DIR/$FILTER" "$FILTER_DIR/$FILTER.bak"
fi
install -m 755 -o root -g root "$FILTER" "$FILTER_DIR/$FILTER"
echo "Installed $FILTER_DIR/$FILTER (previous kept as $FILTER.bak)"

for q in "${QUEUES[@]}"; do
    if [ "$FILTER_ONLY" -eq 0 ]; then
        cp -p "$PPD_DIR/$q.ppd" "$PPD_DIR/$q.ppd.bak"
        # CUPS carries the queue's current default choices over to the new PPD
        lpadmin -p "$q" -P "$PPD"
        echo "Installed $PPD for queue $q (previous kept as $PPD_DIR/$q.ppd.bak)"
    fi
    lpstat -p "$q"
    lpoptions -p "$q" -l | grep -E '^(PageSize|PrintMode)'
done

if [ -n "$TEST_FILE" ]; then
    lp -d "${QUEUES[0]}" -t "install.sh test" "$TEST_FILE"
fi
