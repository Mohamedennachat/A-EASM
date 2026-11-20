"""EASM showcase backend - serves the SPA, reads the Postgres state layer, and
triggers the n8n pipeline through its production webhook so every scan shows up
as a live execution in the n8n UI."""
import os
import time
import threading
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

PG = dict(
    host=os.environ.get("POSTGRES_HOST", "postgres"),
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
    dbname=os.environ.get("POSTGRES_DB", "easm"),
    user=os.environ.get("POSTGRES_USER", "easm"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)
SCANNER_URL = os.environ.get("SCANNER_URL", "http://easm_scanner:5001")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "http://easm_n8n:5678/webhook/run-easm")
N8N_TEST_WEBHOOK_URL = os.environ.get("N8N_TEST_WEBHOOK_URL", "http://easm_n8n:5678/webhook-test/run-easm")
SCAN_TIMEOUT = int(os.environ.get("SCAN_TIMEOUT", "1800"))
STAGES = [
    "Passive discovery (subfinder + crt.sh)",
    "TLS certificates (tlsx)",
    "Recon enrichment (httpx + naabu + shodan)",
    "Vulnerability scan (nuclei)",
    "Fingerprinting (nikto)",
    "XSS (dalfox)",
    "SQL injection (sqlmap)",
    "Diff engine → Postgres → alerts",
]
SERVICES = {
    "n8n (orchestrator)": "http://easm_n8n:5678/healthz",
    "scanner": SCANNER_URL + "/healthz",
    "prometheus": "http://easm_prometheus:9090/-/healthy",
    "grafana": "http://easm_grafana:3000/api/health",
}

app = FastAPI(title="EASM Showcase")
_scan = {"running": False, "started_at": None, "start_runs": 0, "start_scan_id": 0, "last_error": None}
_lock = threading.Lock()


# ── helpers ──────────────────────────────────────────────────────────
def query(sql, args=None, one=False):
    conn = psycopg2.connect(**PG)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, args or ())
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()


def exec_sql(sql, args=None):
    conn = psycopg2.connect(**PG)
    try:
        cur = conn.cursor()
        cur.execute(sql, args or ())
        conn.commit()
    finally:
        conn.close()


def scanner_runs():
    try:
        with urllib.request.urlopen(SCANNER_URL + "/metrics", timeout=3) as r:
            for line in r.read().decode().splitlines():
                if line.startswith("easm_scanner_runs_total "):
                    return int(float(line.split()[1]))
    except Exception:
        pass
    return 0


def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def _last_scan_id():
    row = query("SELECT max(id) AS m FROM scan_summary", one=True)
    return row["m"] if row and row["m"] is not None else 0


def _scan_finished():
    # a webhook-triggered run is done once a fresh scan_summary row lands
    # (the diff-engine stage writes it), or after a hard safety timeout.
    if not _scan["started_at"]:
        return True
    if _last_scan_id() > _scan["start_scan_id"]:
        return True
    return (time.time() - _scan["started_at"]) > SCAN_TIMEOUT


# ── data endpoints ───────────────────────────────────────────────────
@app.get("/api/overview")
def overview():
    counts = query(
        "SELECT (SELECT count(*) FROM domains WHERE status='active') active_domains,"
        " (SELECT count(*) FROM domains) total_domains,"
        " (SELECT count(*) FROM findings) findings,"
        " (SELECT count(*) FROM findings WHERE status<>'resolved' AND severity IN ('critical','high')) crit_high,"
        " (SELECT count(*) FROM scan_assets) assets,"
        " (SELECT count(*) FROM scan_summary) scans", one=True)
    last = query("SELECT scan_timestamp, new_findings_count, requires_alert, critical_count,"
                 " high_count, medium_count, confirmed_xss_count, confirmed_sqli_count, expiring_soon_count"
                 " FROM scan_summary ORDER BY id DESC LIMIT 1", one=True)
    services = {name: http_ok(url) for name, url in SERVICES.items()}
    services["postgres"] = _pg_ok()
    return {"counts": counts, "last_scan": last, "services": services, "stages": STAGES}


def _pg_ok():
    try:
        query("SELECT 1")
        return True
    except Exception:
        return False


@app.get("/api/domains")
def domains():
    return query("SELECT domain, status, priority, last_scanned, created_at FROM domains ORDER BY priority, domain")


class DomainIn(BaseModel):
    domain: str
    priority: int = 1


@app.post("/api/domains")
def add_domain(d: DomainIn):
    dom = d.domain.strip().lower()
    if not dom or " " in dom or "/" in dom:
        raise HTTPException(400, "invalid domain")
    exec_sql("INSERT INTO domains (domain, status, priority) VALUES (%s,'active',%s) ON CONFLICT (domain) DO NOTHING",
             (dom, d.priority))
    return {"ok": True, "domain": dom}


@app.post("/api/domains/{domain}/toggle")
def toggle_domain(domain: str):
    row = query("SELECT status FROM domains WHERE domain=%s", (domain,), one=True)
    if not row:
        raise HTTPException(404, "not found")
    new = "inactive" if row["status"] == "active" else "active"
    exec_sql("UPDATE domains SET status=%s WHERE domain=%s", (new, domain))
    return {"ok": True, "status": new}


@app.delete("/api/domains/{domain}")
def del_domain(domain: str):
    exec_sql("DELETE FROM domains WHERE domain=%s", (domain,))
    return {"ok": True}


@app.get("/api/findings")
def findings(limit: int = 200):
    return query(
        "SELECT category, severity, host, url, identifier, title, status, times_seen,"
        " first_seen, last_seen FROM findings ORDER BY"
        " CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2"
        " WHEN 'low' THEN 3 ELSE 4 END, last_seen DESC LIMIT %s", (limit,))


@app.get("/api/assets")
def assets():
    return query(
        "SELECT host, ip, port, scheme, status_code, title, webserver, tech, source FROM scan_assets"
        " WHERE scan_timestamp=(SELECT max(scan_timestamp) FROM scan_assets) ORDER BY source, host, port")


@app.get("/api/certs")
def certs():
    return query(
        "SELECT host, common_name, issuer, not_after, days_until_expiry, is_expired, expiring_soon"
        " FROM scan_certificates WHERE scan_timestamp=(SELECT max(scan_timestamp) FROM scan_certificates)"
        " ORDER BY days_until_expiry NULLS LAST")


@app.get("/api/scans")
def scans():
    return query(
        "SELECT id, scan_timestamp, critical_count, high_count, medium_count, confirmed_xss_count,"
        " confirmed_sqli_count, expiring_soon_count, new_findings_count, requires_alert, duration_seconds"
        " FROM scan_summary ORDER BY scan_timestamp DESC LIMIT 25")


@app.get("/api/scans/{scan_id}")
def scan_detail(scan_id: int):
    s = query("SELECT * FROM scan_summary WHERE id=%s", (scan_id,), one=True)
    if not s:
        raise HTTPException(404, "scan not found")
    ts = s["scan_timestamp"]
    vulns = query("SELECT host, url, template_id, template_name, severity FROM scan_vulnerabilities"
                  " WHERE scan_timestamp=%s ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
                  " WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, host", (ts,))
    certs = query("SELECT host, common_name, issuer, not_after, days_until_expiry, is_expired, expiring_soon"
                  " FROM scan_certificates WHERE scan_timestamp=%s ORDER BY days_until_expiry NULLS LAST", (ts,))
    assets = query("SELECT host, ip, port, scheme, status_code, title, webserver, source FROM scan_assets"
                   " WHERE scan_timestamp=%s ORDER BY source, host, port", (ts,))
    xss = query("SELECT url, parameter, xss_type, confirmed FROM scan_xss WHERE scan_timestamp=%s", (ts,))
    sqli = query("SELECT url, parameter, dbms, technique FROM scan_sqli WHERE scan_timestamp=%s", (ts,))
    hosts = sorted({a["host"] for a in assets if a["host"]} | {v["host"] for v in vulns if v["host"]}
                   | {c["host"] for c in certs if c["host"]})
    return {"summary": s, "hosts_scanned": hosts, "vulnerabilities": vulns,
            "certificates": certs, "assets": assets, "xss": xss, "sqli": sqli}


# ── scan trigger + progress ──────────────────────────────────────────
@app.post("/api/scan/run")
def run_scan(watch: bool = False):
    # watch=true drives n8n's *test* webhook, so an editor that's armed with
    # "Execute workflow" animates the canvas live; otherwise the production
    # webhook runs the pipeline in the background (still shown in Executions).
    url = N8N_TEST_WEBHOOK_URL if watch else N8N_WEBHOOK_URL
    with _lock:
        if _scan["running"] and not _scan_finished():
            raise HTTPException(409, "a scan is already running")
        try:
            req = urllib.request.Request(
                url, data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
        except urllib.error.HTTPError as e:
            _scan["last_error"] = f"webhook HTTP {e.code}"
            if watch:
                raise HTTPException(409, "watch mode needs the n8n editor armed: open the "
                                    "workflow in n8n, click 'Execute workflow', then Run Scan") from e
            raise HTTPException(502, "n8n did not accept the trigger - is the workflow "
                                "active? run 'make provision' to (re)publish it") from e
        except Exception as e:  # noqa: BLE001
            _scan["last_error"] = str(e)
            raise HTTPException(500, f"failed to trigger workflow: {e}")
        _scan.update(running=True, started_at=time.time(),
                     start_runs=scanner_runs(), start_scan_id=_last_scan_id(),
                     last_error=None)
        return {"started": True, "watch": watch}


@app.get("/api/scan/status")
def scan_status():
    if _scan["running"] and _scan_finished():
        _scan["running"] = False
    running = _scan["running"]
    delta = max(0, scanner_runs() - _scan["start_runs"]) if _scan["started_at"] else 0
    if running:
        stage_index = min(max(delta - 1, 0), len(STAGES) - 1) if delta else 0
    elif _scan["started_at"]:
        stage_index = len(STAGES)  # done
    else:
        stage_index = -1
    last = query("SELECT scan_timestamp, new_findings_count, requires_alert FROM scan_summary"
                 " ORDER BY id DESC LIMIT 1", one=True)
    return {
        "running": running,
        "stage_index": stage_index,
        "stages": STAGES,
        "elapsed": int(time.time() - _scan["started_at"]) if _scan["started_at"] else 0,
        "scanner_runs_delta": delta,
        "last_scan": last,
        "last_error": _scan["last_error"],
    }


# ── static SPA ───────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
