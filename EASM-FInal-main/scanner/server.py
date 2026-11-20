#!/usr/bin/env python3
"""Minimal HTTP-to-shell executor for the EASM scanner container.

Endpoints
    POST /run      {"cmd": "<shell pipeline>", "timeout": <secs?>}
                   -> {"stdout","stderr","exit_code","duration_seconds"}
    GET  /healthz  -> {"status":"ok"}
    GET  /metrics  -> Prometheus text exposition

This service deliberately executes arbitrary shell commands and is therefore
only ever bound to the internal Docker network (never published to the host).
Runs as the non-root `scanner` user.
"""
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("SCANNER_PORT", "5001"))
DEFAULT_TIMEOUT = int(os.environ.get("RUN_TIMEOUT", "1200"))

_metrics = {"runs_total": 0, "runs_failed": 0, "run_seconds_total": 0.0}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, json.dumps({"status": "ok"}))
        elif self.path == "/metrics":
            m = _metrics
            out = (
                "# HELP easm_scanner_runs_total Total /run invocations\n"
                "# TYPE easm_scanner_runs_total counter\n"
                f"easm_scanner_runs_total {m['runs_total']}\n"
                "# HELP easm_scanner_runs_failed_total Runs that failed or timed out\n"
                "# TYPE easm_scanner_runs_failed_total counter\n"
                f"easm_scanner_runs_failed_total {m['runs_failed']}\n"
                "# HELP easm_scanner_run_seconds_total Cumulative run wall-time\n"
                "# TYPE easm_scanner_run_seconds_total counter\n"
                f"easm_scanner_run_seconds_total {m['run_seconds_total']:.3f}\n"
            )
            self._send(200, out, "text/plain; version=0.0.4")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/run":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as exc:  # noqa: BLE001
            self._send(400, json.dumps({"error": f"bad json: {exc}"}))
            return

        cmd = payload.get("cmd")
        if not cmd:
            self._send(400, json.dumps({"error": "missing cmd"}))
            return
        timeout = int(payload.get("timeout", DEFAULT_TIMEOUT))

        _metrics["runs_total"] += 1
        start = time.time()
        try:
            proc = subprocess.run(
                ["/bin/bash", "-c", cmd],
                capture_output=True, text=True, timeout=timeout,
            )
            dur = time.time() - start
            _metrics["run_seconds_total"] += dur
            if proc.returncode != 0 and not proc.stdout:
                _metrics["runs_failed"] += 1
            self._send(200, json.dumps({
                "stdout": proc.stdout,
                "stderr": proc.stderr[-4000:],
                "exit_code": proc.returncode,
                "duration_seconds": round(dur, 3),
            }))
        except subprocess.TimeoutExpired as exc:
            _metrics["runs_failed"] += 1
            partial = exc.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode(errors="replace")
            self._send(200, json.dumps({
                "stdout": partial,
                "stderr": f"timeout after {timeout}s",
                "exit_code": 124,
                "duration_seconds": timeout,
            }))

    def log_message(self, *args):  # silence default stderr logging
        return


if __name__ == "__main__":
    print(f"easm_scanner executor listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
