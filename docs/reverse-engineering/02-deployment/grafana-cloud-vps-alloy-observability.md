# Grafana Cloud observability for the Runr VPS

Grafana Alloy runs on the `runr-vps` host and sends host metrics to Grafana Cloud Metrics and system logs to Grafana Cloud Logs. The Grafana **Linux node / overview** dashboard visualizes the host metrics. This is infrastructure monitoring; it is separate from Runr's application-level telemetry.

## Credential names and handling

Application-level checks were installed on 2026-09-26. Read [vps-acquisition-operating-policy.md](vps-acquisition-operating-policy.md) for per-source outcomes, agent JSON queries, the timer guard, and the publisher's shared catalog binding. The prepared dashboard is `deploy/vps-observability/dashboard.json`.

- Local staging file: `user_config/grafana-cloud-alloy-vps-token.txt`. It contains only the Grafana Cloud access-policy token value, with no quotes, key name, or other text. This is a local secret file and must never be committed, printed, or pasted into chat.
- Recommended Grafana token display name: `runr-vps-prod-alloy-telemetry`. This is metadata in Grafana, not part of the token value. Do not rotate a working token solely to change its display name.
- The local file is a staging copy for an operator/agent. The live VPS service reads `GCLOUD_RW_API_KEY` from `/etc/systemd/system/alloy.service.d/env.conf`; that file is root-owned and mode `0600`.
- The systemd drop-in must contain a `[Service]` section followed by `Environment="GCLOUD_RW_API_KEY=..."`. Without `[Service]`, systemd ignores the setting and Alloy receives no credential, causing Grafana to reject metric and log writes with HTTP 401.
- Do not put this token in `user_config/.env`. That file is for Runr application settings; Alloy runs as a separate systemd service.
- The token's Grafana access policy must include `set:alloy-data-write`. The token grants Alloy permission to write host telemetry.

## Operations and verification

The Alloy configuration is `/etc/alloy/config.alloy`; the service is `alloy.service`.

```sh
sudo systemctl is-active alloy.service
sudo systemctl is-enabled alloy.service
curl --fail http://127.0.0.1:12345/-/ready
```

For delivery checks, inspect Alloy's own metrics at `http://127.0.0.1:12345/metrics`. Successful `prometheus_remote_storage_samples_total` / `prometheus_remote_storage_bytes_total` and `loki_write_sent_entries_total`, with zero recent failed samples and dropped log entries, confirm successful writes. Refresh the Grafana Linux node dashboard after data has had time to arrive.

Never run `systemctl cat alloy.service` in a context where its output may be shown: it can print the credential from the systemd drop-in. Use `systemctl show` only for non-secret status fields, and never request the `Environment` property in displayed output.
