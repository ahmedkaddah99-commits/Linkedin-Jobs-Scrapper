#!/bin/bash
# Fixed-size capacity receipt and metrics; no deletion of unarchived data.
set -euo pipefail
umask 022
install -d -m 0755 /var/lib/runr/storage-budget
available=$(df -B1 --output=avail / | tail -n 1 | tr -d ' ')
used=$(df -B1 --output=used / | tail -n 1 | tr -d ' ')
warning=0
test "$available" -ge 32212254720 || warning=1
exports=$(du -x -s -B1 /srv/runr/exports | cut -f 1)
releases=$(du -x -s -B1 /srv/runr/releases | cut -f 1)
history_warning=0
test "$exports" -le 6442450944 && test "$releases" -le 4294967296 || history_warning=1
printf 'runr_host_storage_available_bytes %s\nrunr_host_storage_used_bytes %s\nrunr_host_storage_headroom_warning %s\nrunr_export_storage_bytes %s\nrunr_release_storage_bytes %s\nrunr_history_storage_budget_warning %s\n' "$available" "$used" "$warning" "$exports" "$releases" "$history_warning" > /var/lib/runr/storage-budget/storage.prom.tmp
mv /var/lib/runr/storage-budget/storage.prom.tmp /var/lib/runr/storage-budget/storage.prom
{ date -u --iso-8601=seconds; df -h /; du -x -h -s /srv/runr/backups /srv/runr/exports /srv/runr/releases; } > /var/lib/runr/storage-budget/latest.txt.tmp
mv /var/lib/runr/storage-budget/latest.txt.tmp /var/lib/runr/storage-budget/latest.txt
if [ "$warning" = 1 ]; then echo 'Runr disk headroom below 30 GiB: archive historical copies before deleting.' >&2; exit 1; fi
if [ "$history_warning" = 1 ]; then echo 'Runr history budget exceeded: exports >6 GiB or releases >4 GiB; archive before pruning.' >&2; exit 1; fi
