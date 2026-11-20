# syntax=docker/dockerfile:1

# ─────────────────────────────────────────────────────────────
# Stage 1 - compile the Go-based ProjectDiscovery / dalfox tools
# ─────────────────────────────────────────────────────────────
FROM golang:1.26-bookworm AS gobuild
ENV CGO_ENABLED=1 GOBIN=/out GOTOOLCHAIN=auto
# naabu needs libpcap to build (raw packet capture)
RUN apt-get update && apt-get install -y --no-install-recommends libpcap-dev \
 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /out \
 && go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest \
 && go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest \
 && go install -v github.com/projectdiscovery/tlsx/cmd/tlsx@latest \
 && go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest \
 && go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest \
 && go install -v github.com/hahwul/dalfox/v2@latest

# ─────────────────────────────────────────────────────────────
# Stage 2 - slim runtime with all scanners + the /run executor
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/tools:/usr/local/bin:${PATH}" \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash ca-certificates curl git jq openssl \
      libpcap0.8 \
      perl libnet-ssleay-perl libjson-perl libxml-writer-perl \
      nmap \
 && rm -rf /var/lib/apt/lists/*

# Go tool binaries from the build stage
COPY --from=gobuild /out/ /opt/tools/

# sqlmap (active SQLi)
RUN git clone --depth 1 https://github.com/sqlmapproject/sqlmap.git /opt/sqlmap \
 && printf '#!/bin/sh\nexec python3 /opt/sqlmap/sqlmap.py "$@"\n' > /usr/local/bin/sqlmap \
 && chmod +x /usr/local/bin/sqlmap

# nikto (fingerprinting / misconfig)
RUN git clone --depth 1 https://github.com/sullo/nikto.git /opt/nikto \
 && printf '#!/bin/sh\nexec perl /opt/nikto/program/nikto.pl "$@"\n' > /usr/local/bin/nikto \
 && chmod +x /usr/local/bin/nikto

# xssmap compatibility shim (backed by dalfox)
COPY shims/xssmap.py /opt/xssmap/xssmap.py

# executor + entrypoint
COPY server.py /opt/server.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh /opt/xssmap/xssmap.py

# least-privilege: run as non-root (matches thesis hardening)
RUN useradd -m -u 10001 scanner \
 && mkdir -p /home/scanner/.config/subfinder /home/scanner/nuclei-templates \
 && chown -R scanner:scanner /home/scanner /opt/xssmap /opt/sqlmap /opt/nikto
USER scanner
WORKDIR /home/scanner

EXPOSE 5001
ENTRYPOINT ["/opt/entrypoint.sh"]
