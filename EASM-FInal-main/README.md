# Automated External Attack Surface Management (A-EASM) Pipeline

A self-hosted, open-source, **stateful** EASM pipeline orchestrated by **n8n**: it
continuously discovers external assets, fingerprints and scans them, suppresses
already-known findings with a PostgreSQL **diff engine**, and routes only *new*
findings to Discord, email, and Jira. The whole stack runs from a single
`docker compose up`.

> Thesis project (EPITA, group CS03). This repository is the reproducible
> implementation that accompanies the report `C03_ Project-(A-EASM).pdf`.

---

## Architecture

```
Schedule / Manual ─▶ Postgres(domains) ─▶ Passive Discovery (subfinder + crt.sh)
   ─▶ Web targets ─┬─▶ tlsx (certs) ───────────────────────────────┐
                   ├─▶ httpx + naabu + Shodan (recon enrichment) ───┤
                   └─▶ nuclei ─▶ nikto ─▶ xssmap(dalfox) ─▶ sqlmap ─┤
                                                                    ▼
        Merge ─▶ DIFF ENGINE (findings upsert, alert only on NEW) ─▶ Postgres(history)
                                                                    ▼
                                        IF new findings ──▶ Email + Discord + Jira
```

Every scanner runs inside the **`easm_scanner`** container, invoked over an
internal HTTP `/run` endpoint. That container is never published to the host - it
is an arbitrary-command execution service and lives only on the closed
`easm_internal` Docker network, as non-root (`scanner`, uid 10001).

### Components

| Service | Image | Exposed | Role |
|---|---|---|---|
| `postgres` | postgres:16-alpine | 127.0.0.1:5432 | State + diff engine |
| `easm_scanner` | built locally | **none (internal)** | subfinder, crt.sh, httpx, naabu, tlsx, nuclei, nikto, dalfox(xssmap), sqlmap + `/run` executor |
| `n8n` | n8nio/n8n | 127.0.0.1:5678 | Orchestrator |
| `prometheus` | prom/prometheus | 127.0.0.1:9090 | Metrics store |
| `otel-collector` | otel-collector-contrib | internal | Telemetry pipeline |
| `grafana` | grafana/grafana | 127.0.0.1:3000 | Dashboards |

---

## Quick start

```bash
cp .env.example .env      # then fill in secrets (see below)
make up                   # build scanner + frontend, start the stack (first run pulls images + clones nuclei templates)
make provision            # import n8n credentials + the workflow
```

Then open the **Control Center → http://localhost:8080** - the one-stop UI: add a
target, click **Run Scan**, watch the 8 pipeline stages light up live, then browse
findings (new vs. known), assets, certificates, and the scan-history diff view.

Other UIs:
- **n8n** → http://localhost:5678 (the workflow graph; set an owner account on first visit)
- **Grafana** → http://localhost:3000 (user `admin`, password from `GRAFANA_ADMIN_PASSWORD`)
- **Prometheus** → http://localhost:9090
- Headless run (no UI): `make run`

### Control Center (`app/`)
A FastAPI + vanilla-JS single-page app that ties the whole pipeline together:
reads the Postgres state layer, triggers the n8n workflow through its `run-easm`
production webhook (so each **Run Scan** is a real n8n execution you can watch in
n8n's Executions view), and polls the scanner's `/metrics` to render live
stage-by-stage progress. It's the "complete user pipeline" view: target → scan →
discover → findings → diff → alert.

Tick **Watch in n8n** in the header to route Run Scan through n8n's *test* webhook
instead: open the workflow in n8n, click **Execute workflow** to arm it, then Run
Scan to watch the nodes light up live on the canvas.

### Required secrets (`.env`)

| Variable | Notes |
|---|---|
| `POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY`, `GRAFANA_ADMIN_PASSWORD` | local to your machine; any strong value, keep stable |
| `DISCORD_WEBHOOK_URL` | the alert channel |
| `SHODAN_API_KEY` | optional; recon enrichment degrades gracefully without credits |
| `GITHUB_TOKEN` | feeds subfinder's GitHub source |
| `SMTP_*` | Gmail needs a **16-char App Password**, not the account password |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_ID`, `JIRA_TASK_ISSUETYPE_ID` | see *Jira* below |

### Getting a working `.env` (for teammates)

`.env` is **gitignored and never committed** - the repo only ships `.env.example`
with placeholders. Cloning gives you the code, not the credentials, so after
`cp .env.example .env` you still need to fill it in:

- **Ask a teammate for the shared secrets** (Discord DM, a private channel, or a
  vault - never GitHub). These must match what the team uses so everyone hits the
  same channels: `DISCORD_WEBHOOK_URL`, `SMTP_*`, `EMAIL_*`, and every `JIRA_*`
  value.
- **Set your own local-only values** - anything on your machine works:
  `POSTGRES_PASSWORD` (any strong string), `N8N_ENCRYPTION_KEY`
  (`openssl rand -hex 24`), `GRAFANA_ADMIN_PASSWORD`.
- **Optional, degrade gracefully if left blank**: `SHODAN_API_KEY`, `GITHUB_TOKEN`.

Without the shared secrets the stack still comes up and the core pipeline
(scan → diff → Control Center → Grafana) works fully; only alert **delivery** to
Discord, email, and Jira stays silent until they are set. Never commit your
filled-in `.env`.

---

## The diff engine (alert-fatigue suppression)

Each finding is reduced to a stable `finding_key`
(`category|host|identifier|url`) and upserted into the `findings` table:

```sql
INSERT INTO findings (...) VALUES (...)
ON CONFLICT (finding_key) DO UPDATE SET last_seen = now(), times_seen = times_seen + 1
RETURNING finding_key, (xmax = 0) AS is_new;
```

`xmax = 0` is true only for rows that were just **inserted**, i.e. genuinely new.
Alerts (and Jira tickets) fire **only** for new findings; the full scan history is
still written to `scan_*` tables every run. This is the stateful behaviour the
thesis describes - the original exported workflow did not implement it.

---

## Targets & authorization

Seeded targets (`db/init/02_seed.sql`) are **public, scanning-sanctioned** demo
apps: `testfire.net` (AltoroMutual), `ginandjuice.shop`, `public-firing-range`,
`scanme.nmap.org`.

**Do not** point the active scanners (sqlmap, dalfox, nikto, nuclei) at hosts you
don't own or aren't authorized to test. `epita.net` / `epita.fr` are intentionally
**not** seeded - only add them on an authorized network with the signed scanning
authorization in hand.

---

## Observability

`N8N_METRICS=true` exposes n8n's Prometheus metrics; the scanner exposes
`/metrics`. The OTel Collector scrapes both and re-exports them; Prometheus stores
them; Grafana provisions a Prometheus datasource, an EASM-Postgres datasource, and
an EASM dashboard.

---

## Known caveats

- **Jira**: wired to project **EASME** ("EASM Alert") on `ibrahimjarekji.atlassian.net`
  (project id `10033`, Task issue-type `10039`, account `ibrahim.jarekji@epita.fr`).
  New findings create tickets there. The node is still `onError: continueRegularOutput`,
  so a Jira hiccup never blocks a scan.
- **sqlmap** only reports *confirmed* injections; hardened/WAF'd live demo targets
  may yield none even when other tools find plenty.
- **Secrets** committed to `.env` during the build were shared in plaintext -
  rotate the Discord webhook, Shodan key, GitHub token, Gmail app password, and
  Jira token before any real use.

---

## Make targets

| Command | Action |
|---|---|
| `make up` | build + start the stack |
| `make provision` | import credentials + workflow into n8n |
| `make run` | trigger one pipeline run |
| `make logs` | tail all logs |
| `make down` / `make reset` | stop / stop + wipe volumes |
