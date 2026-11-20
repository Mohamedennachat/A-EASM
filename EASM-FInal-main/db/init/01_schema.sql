-- =====================================================================
--  EASM PostgreSQL state layer
--  Loaded automatically by the postgres container on first init.
-- =====================================================================

-- ── Asset register ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS domains (
    id           BIGSERIAL PRIMARY KEY,
    domain       TEXT        NOT NULL UNIQUE,
    status       TEXT        NOT NULL DEFAULT 'active',
    priority     INT         NOT NULL DEFAULT 3,
    last_scanned TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Per-run summary ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scan_summary (
    id                   BIGSERIAL PRIMARY KEY,
    scan_timestamp       TIMESTAMPTZ NOT NULL,
    total_certs_scanned  INT DEFAULT 0,
    expiring_soon_count  INT DEFAULT 0,
    expired_count        INT DEFAULT 0,
    critical_count       INT DEFAULT 0,
    high_count           INT DEFAULT 0,
    medium_count         INT DEFAULT 0,
    confirmed_xss_count  INT DEFAULT 0,
    confirmed_sqli_count INT DEFAULT 0,
    total_exploits_found INT DEFAULT 0,
    new_findings_count   INT DEFAULT 0,
    requires_alert       BOOLEAN DEFAULT false,
    started_at           TIMESTAMPTZ,
    duration_seconds     INT
);

-- ── Full scan history (append-only) ───────────────────────────────
CREATE TABLE IF NOT EXISTS scan_vulnerabilities (
    id             BIGSERIAL PRIMARY KEY,
    host           TEXT,
    url            TEXT,
    template_id    TEXT,
    template_name  TEXT,
    severity       TEXT,
    description    TEXT,
    scan_timestamp TIMESTAMPTZ NOT NULL,
    requires_alert BOOLEAN DEFAULT false,
    UNIQUE (host, template_id, url, scan_timestamp)
);

CREATE TABLE IF NOT EXISTS scan_certificates (
    id                BIGSERIAL PRIMARY KEY,
    host              TEXT,
    common_name       TEXT,
    issuer            TEXT,
    not_after         TEXT,
    days_until_expiry INT,
    is_expired        BOOLEAN,
    expiring_soon     BOOLEAN,
    scan_timestamp    TIMESTAMPTZ NOT NULL,
    UNIQUE (host, common_name, not_after, scan_timestamp)
);

CREATE TABLE IF NOT EXISTS scan_xss (
    id             BIGSERIAL PRIMARY KEY,
    url            TEXT,
    parameter      TEXT,
    payload        TEXT,
    xss_type       TEXT,
    severity       TEXT,
    confirmed      BOOLEAN,
    scan_timestamp TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_sqli (
    id             BIGSERIAL PRIMARY KEY,
    url            TEXT,
    parameter      TEXT,
    injection_type TEXT,
    dbms           TEXT,
    dbms_version   TEXT,
    technique      TEXT,
    severity       TEXT,
    confirmed      BOOLEAN,
    scan_timestamp TIMESTAMPTZ NOT NULL
);

-- ── Recon / fingerprint assets (httpx + naabu + shodan) ───────────
CREATE TABLE IF NOT EXISTS scan_assets (
    id             BIGSERIAL PRIMARY KEY,
    host           TEXT,
    ip             TEXT,
    port           INT,
    scheme         TEXT,
    status_code    INT,
    title          TEXT,
    webserver      TEXT,
    tech           TEXT,
    source         TEXT,            -- httpx | naabu | shodan
    scan_timestamp TIMESTAMPTZ NOT NULL
);

-- ── Stateful diff engine ──────────────────────────────────────────
-- One row per *distinct* finding across all time. The workflow upserts
-- here; the RETURNING (xmax = 0) trick reveals whether the row was just
-- inserted (genuinely NEW) versus already known, so only new findings
-- raise alerts. This is the alert-fatigue-suppression layer the thesis
-- describes but the original JSON never implemented.
CREATE TABLE IF NOT EXISTS findings (
    id           BIGSERIAL PRIMARY KEY,
    finding_key  TEXT        NOT NULL UNIQUE,
    category     TEXT        NOT NULL,            -- vuln | xss | sqli | cert
    host         TEXT,
    url          TEXT,
    identifier   TEXT,                            -- template_id | parameter | common_name
    severity     TEXT,
    title        TEXT,
    details      JSONB,
    status       TEXT        NOT NULL DEFAULT 'new',  -- new | active | resolved
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    times_seen   INT         NOT NULL DEFAULT 1
);

-- ── Indexes ───────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_vuln_ts      ON scan_vulnerabilities(scan_timestamp);
CREATE INDEX IF NOT EXISTS idx_cert_ts      ON scan_certificates(scan_timestamp);
CREATE INDEX IF NOT EXISTS idx_xss_ts       ON scan_xss(scan_timestamp);
CREATE INDEX IF NOT EXISTS idx_sqli_ts      ON scan_sqli(scan_timestamp);
CREATE INDEX IF NOT EXISTS idx_findings_status   ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_lastseen ON findings(last_seen);
CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);
