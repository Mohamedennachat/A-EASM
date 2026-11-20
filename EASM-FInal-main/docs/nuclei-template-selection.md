# Nuclei Template Selection

The Nuclei stage runs against every live web target discovered in a cycle. To
balance **coverage** against **scan time** and **false positives**, the pipeline
filters the ~13,000-template community set (cloned at container start from
`projectdiscovery/nuclei-templates`) down by **tag** and **severity** rather than
running everything.

## Active selection

`nuclei -silent -jsonl -tags cve,ssl,exposure -severity critical,high,medium,low -timeout 5`

| Tag | Why it's included |
|---|---|
| `cve` | Known CVEs on internet-facing services - the core EASM signal (fast exploitation window after disclosure). |
| `ssl` | TLS/cipher misconfigurations (deprecated TLS, weak ciphers) - complements the dedicated `tlsx` cert stage. |
| `exposure` | Exposed panels, config files, backups, `.git`, tokens - classic external-attack-surface leakage. |

| Severity | Rationale |
|---|---|
| `critical`, `high` | Always alerted + ticketed. |
| `medium` | Stored and trended; alerted via the diff engine when *new*. |
| `low` | Stored for context (e.g. weak-cipher), not individually escalated. |

`info` severity is intentionally excluded from escalation to avoid alert fatigue -
detections like WAF/technology fingerprints are captured by the `httpx` enrichment
stage instead.

## Why tag-filtering (not all templates)

- **Time-bounded:** a full 13k-template run per host is too slow for a continuous
  cadence; the CVE/SSL/exposure subset is the high-signal core.
- **`-timeout 5`** caps per-request latency so one slow host can't stall a cycle.
- **Extensible:** add `-tags misconfig,default-login` (or specific
  `-id <template-id>`) to widen coverage when scanning your own authorized estate.

## Tuning knobs

Edit the `Nuclei Scan` node's command in `n8n/workflow.json`:
- Add tags: `…,misconfig,default-logins,takeover`
- Restrict to KEV/most-critical only: `-tags cve -severity critical`
- Rate-limit a fragile target: append `-rate-limit 50 -c 25`
