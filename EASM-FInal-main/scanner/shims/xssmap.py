#!/usr/bin/env python3
"""xssmap compatibility shim - backed by dalfox.

The original workflow shells out to a custom `xssmap.py`. We reproduce its
CLI/JSON contract on top of the maintained `dalfox` scanner so the existing
n8n "Parse XSS Output" node keeps working unchanged.

CLI (matches the workflow node):
    xssmap.py --url <URL> [--level N] [--output json] [--timeout SECS]

Output (one JSON object on stdout):
    {"url": <URL>, "vulnerabilities": [
        {"url","parameter","payload","type","confirmed"}, ...
    ]}
"""
import argparse
import json
import subprocess
import sys


def main() -> None:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--url", required=True)
    ap.add_argument("--level", default="1")
    ap.add_argument("--output", default="json")
    ap.add_argument("--timeout", default="10")
    args, _ = ap.parse_known_args()

    try:
        per_req = int(args.timeout)
    except ValueError:
        per_req = 10

    vulns = []
    try:
        proc = subprocess.run(
            ["dalfox", "url", args.url,
             "--format", "json", "--silence", "--no-color", "--no-spinner",
             "--timeout", str(per_req)],
            capture_output=True, text=True, timeout=per_req * 20 + 60,
        )
        raw = (proc.stdout or "").strip()
        if raw:
            data = json.loads(raw)
            for poc in (data if isinstance(data, list) else []):
                if not isinstance(poc, dict) or not poc:
                    continue  # dalfox emits [{}] when nothing is found
                payload = poc.get("payload") or ""
                poc_url = poc.get("data") or ""
                if not payload and not poc_url:
                    continue
                kind = str(poc.get("type", "")).upper()
                vulns.append({
                    "url": poc_url or args.url,
                    "parameter": poc.get("param", ""),
                    "payload": payload or poc_url,
                    "type": str(poc.get("inject_type", "reflected") or "reflected").lower(),
                    # dalfox marks verified findings with type "V" (and grep hits "G")
                    "confirmed": kind in ("V", "G"),
                })
    except Exception as exc:  # noqa: BLE001 - never crash the pipeline stage
        print(json.dumps({"url": args.url, "vulnerabilities": [], "error": str(exc)}))
        return

    print(json.dumps({"url": args.url, "vulnerabilities": vulns}))


if __name__ == "__main__":
    main()
