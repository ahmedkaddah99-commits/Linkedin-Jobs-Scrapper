#!/bin/bash
set -euo pipefail
# Remove only this transfer's include; preserve subsequent nginx edits.
sed -i '\@include /etc/nginx/runr-transfer-locations.conf;@d' /etc/nginx/sites-available/runr-public
nginx -t
systemctl reload nginx
rm -f -- /etc/nginx/runr-transfer-locations.conf /etc/nginx/runr-transfer.htpasswd /tmp/runr-transfer-locations.conf
systemctl stop runr-archive-transfer-20261011.service || true
echo 'Temporary archive download routes and credentials removed; source archives preserved.'
