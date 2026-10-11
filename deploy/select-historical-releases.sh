#!/bin/bash
set -euo pipefail
umask 077
root=/srv/runr/ops/releases-archive-20261011
mkdir -p "$root"
test ! -e "$root/history.tar.gz"
find /srv/runr /opt -maxdepth 5 -type l -exec readlink -f '{}' \; > "$root/symlinks.txt"
systemctl list-unit-files 'runr*.service' --no-legend | awk '{print $1}' | while read -r unit; do systemctl show "$unit" -p WorkingDirectory -p ExecStart; done > "$root/effective-units.txt"
: > "$root/protected-newest.txt"
for family in acquisition catalog-storage customer description publication-recovery catalog-deduplication; do
 find /srv/runr/releases -mindepth 1 -maxdepth 1 -type d -name "$family-*" -printf '%T@ %p\n' | sort -rn | head -n 2 | cut -d ' ' -f 2- >> "$root/protected-newest.txt" || true
done
: > "$root/paths.txt"
for path in /srv/runr/releases/*; do
 test -d "$path" && test ! -L "$path" || continue
 grep -F -q "$path" "$root/protected-newest.txt" "$root/symlinks.txt" "$root/effective-units.txt" && continue
 grep -R -F -q "$path" /etc/systemd/system /etc/nginx /etc/runr /opt/runr-ops 2>/dev/null && continue
 lsof -t +D "$path" 2>/dev/null | grep -q . && continue
 printf '%s\n' "${path#/}" >> "$root/paths.txt"
done
cat "$root/paths.txt"
