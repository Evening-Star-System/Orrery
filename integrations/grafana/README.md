# Orrery in Grafana

Orrery is a drift and conformance checker, so it belongs inside the monitoring stack you already run.
This puts "is the fleet still as I declared it" on the same single pane of glass as your CPU, disk, and
app metrics, and alerts through the same Alertmanager.

The reconciler emits Prometheus metrics; you scrape them with Prometheus and graph them in Grafana.

## 1. Emit the metrics on a schedule

`ess-orrery reconcile --format prometheus` writes Prometheus exposition to stdout. Run it on a cron and
write it, atomically, into the node_exporter textfile collector directory:

```sh
# /etc/cron.d/orrery  (every 5 minutes)
*/5 * * * * root ess-orrery reconcile --profile /etc/orrery/prod.toml --format prometheus \
  > /var/lib/node_exporter/textfile_collector/orrery.prom.$$ \
  && mv /var/lib/node_exporter/textfile_collector/orrery.prom.$$ \
        /var/lib/node_exporter/textfile_collector/orrery.prom
```

Start node_exporter with the collector enabled:

```sh
node_exporter --collector.textfile.directory=/var/lib/node_exporter/textfile_collector
```

(No long-running Orrery process is needed. A `/metrics` HTTP endpoint is a possible future option.)

## 2. Scrape and alert

Prometheus already scrapes node_exporter, so the `orrery_*` series appear automatically. Load the alert
rules:

```yaml
# prometheus.yml
rule_files:
  - /etc/prometheus/rules/orrery-alerts.yml   # this repo's integrations/grafana/alerts.yml
```

## 3. Import the dashboard

In Grafana: Dashboards, New, Import, upload `dashboard.json`, and pick your Prometheus data source. You
get a fleet-status tile (In sync / DRIFT), a drift count, worst-severity over time, and a per-check
table, filterable by box.

## Metrics

| Metric | Meaning |
|---|---|
| `orrery_check_status{box,check,subject}` | Per-finding severity: 0 ok, 1 info, 2 warn, 3 drift, 4 fail |
| `orrery_findings{box,severity}` | Count of findings at each severity |
| `orrery_worst_severity{box}` | Worst severity across the run |
| `orrery_clean{box}` | 1 if clean (worst at or below info), else 0 |
| `orrery_drift_total{box}` | Findings at drift or worse (the number to alert on) |
| `orrery_last_run_timestamp_seconds{box}` | When the reconcile ran (freshness) |
| `orrery_up{box}` | 1 when a reconcile produced output |

The labels carry only non-secret identities the reconciler already reports (check ids, box names, and
subjects such as paths or vault-path identities). Secret values are never emitted, the same value-blind
guarantee the engines hold.
