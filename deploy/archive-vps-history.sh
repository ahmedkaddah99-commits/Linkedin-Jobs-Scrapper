#!/bin/bash
# Explicit history only. Copy and verify archive off-host before finalize.
set -euo pipefail
umask 077
label=${RUNR_HISTORY_ARCHIVE_LABEL:-history}
case "$label" in history|releases) ;; *) exit 2 ;; esac
root=/srv/runr/ops/${label}-archive-20261011
mkdir -p "$root"
exec 9>"$root/lock"
flock -n 9
case "${1:-}" in
 prepare)
  test ! -e "$root/history.tar.gz" || { echo 'Archive already exists; inspect before rerun.'; exit 1; }
  if [ "$label" = history ]; then
   printf '%s\n' srv/runr/backups/catalog-storage-20261008 srv/runr/exports/t42-d21a3901 srv/runr/exports/t42-attempt05-20260924 srv/runr/exports/t42-attempt08-20260925 srv/runr/exports/t42-attempt09-20260925 > "$root/paths.txt"
  else
   test -s "$root/paths.txt"
  fi
  # Never select active code, state, customer files or current exports by age.
  while IFS= read -r path; do
   test -d "/$path"
   if lsof -t +D "/$path" 2>/dev/null | grep -q .; then echo "Open files: /$path"; exit 1; fi
  done < "$root/paths.txt"
  df -B1 / > "$root/disk-before.txt"
  tar -C / --null -T <(tr '\n' '\0' < "$root/paths.txt") -cf - | gzip -1 > "$root/history.tar.gz.partial"
  gzip -t "$root/history.tar.gz.partial"
  mv "$root/history.tar.gz.partial" "$root/history.tar.gz"
  sha256sum "$root/history.tar.gz" > "$root/history.sha256"
  tar -tzf "$root/history.tar.gz" > "$root/archive-members.txt"
  echo 'Prepared; download, hash and inspect off-host before finalize.'
 ;;
 finalize)
  expected=${2:?Supply SHA256 verified on local device}
  actual=$(sha256sum "$root/history.tar.gz" | cut -d ' ' -f 1)
  test "$expected" = "$actual"
  test ! -e "$root/finalized.txt"
  # Ensure archived sources have not changed since preparation.
  tar -dzf "$root/history.tar.gz" -C / > "$root/compare.txt" 2>&1
  while IFS= read -r path; do
   case "$path" in
    srv/runr/backups/catalog-storage-20261008|srv/runr/exports/t42-d21a3901|srv/runr/exports/t42-attempt05-20260924|srv/runr/exports/t42-attempt08-20260925|srv/runr/exports/t42-attempt09-20260925) ;;
    srv/runr/releases/*)
     test "$label" = releases
     test "$(dirname "$path")" = srv/runr/releases
     if grep -R -F -q "/$path" /etc/systemd/system /etc/nginx /etc/runr /opt/runr-ops --exclude='paths.txt' 2>/dev/null; then echo 'Release reference found'; exit 1; fi
     ;;
    *) echo 'Unexpected deletion path'; exit 1 ;;
   esac
   if lsof -t +D "/$path" 2>/dev/null | grep -q .; then echo "Open files: /$path"; exit 1; fi
  done < "$root/paths.txt"
  while IFS= read -r path; do rm -rf -- "/$path"; done < "$root/paths.txt"
  printf 'Verified off-host SHA256: %s\nCompleted: %s\n' "$expected" "$(date -u --iso-8601=seconds)" > "$root/finalized.txt"
  rm -- "$root/history.tar.gz"
  df -B1 / > "$root/disk-after.txt"
  cat "$root/disk-after.txt"
 ;;
 *) echo 'Usage: archive-vps-history.sh prepare | finalize LOCAL_VERIFIED_SHA256'; exit 2 ;;
esac
