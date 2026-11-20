#!/bin/bash
set -e

CONF_DIR="$HOME/.config/subfinder"
CONF="$CONF_DIR/provider-config.yaml"
mkdir -p "$CONF_DIR"

# Render subfinder provider config from env (keeps secrets out of the image).
: > "$CONF"
if [ -n "$GITHUB_TOKEN" ]; then
  printf 'github:\n  - %s\n' "$GITHUB_TOKEN" >> "$CONF"
fi
if [ -n "$SHODAN_API_KEY" ]; then
  printf 'shodan:\n  - %s\n' "$SHODAN_API_KEY" >> "$CONF"
fi

# Provision nuclei templates (cached on the mounted volume after first run).
# nuclei -update-templates is unreliable in v3.9; clone the repo directly.
if [ ! -d "$HOME/nuclei-templates/http" ]; then
  echo "[entrypoint] cloning nuclei-templates (first run, ~1 min)…"
  git clone --depth 1 -q https://github.com/projectdiscovery/nuclei-templates.git "$HOME/nuclei-templates" 2>/dev/null \
    || echo "[entrypoint] template clone failed; nuclei stage will be degraded"
fi

exec python3 /opt/server.py
