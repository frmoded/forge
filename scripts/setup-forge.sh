#!/usr/bin/env bash
# setup-forge.sh — bootstrap a new machine for Forge development.
# Idempotent: safe to re-run. Sets up prerequisites + clones repos +
# creates a venv + installs deps. Does NOT start the servers.
#
# Usage:
#   bash setup-forge.sh
#
# After this completes, see the printed "Next steps" at the end.

set -euo pipefail

PROJECTS_DIR="${HOME}/projects"
FORGE_REPO="${PROJECTS_DIR}/forge"
CLIENT_REPO="${PROJECTS_DIR}/forge-moda-client"
CLIENT_APP="${CLIENT_REPO}/forge-moda-web"

echo "=== Forge bootstrap ==="

# --- Homebrew ---
if ! command -v brew >/dev/null 2>&1; then
  echo "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to PATH for the rest of this script (Apple Silicon vs Intel)
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
else
  echo "Homebrew: present."
fi

# --- Node.js ---
if ! command -v node >/dev/null 2>&1; then
  echo "Installing Node.js..."
  brew install node
else
  echo "Node: $(node --version)"
fi

# --- Python 3 ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing Python..."
  brew install python@3.12
else
  echo "Python: $(python3 --version)"
fi

# --- Git ---
if ! command -v git >/dev/null 2>&1; then
  echo "Installing Git..."
  brew install git
else
  echo "Git: $(git --version)"
fi

mkdir -p "${PROJECTS_DIR}"

# --- Forge backend ---
if [ ! -d "${FORGE_REPO}" ]; then
  echo "Cloning forge..."
  git clone https://github.com/frmoded/forge.git "${FORGE_REPO}"
else
  echo "forge: present at ${FORGE_REPO}"
fi

cd "${FORGE_REPO}"
if [ ! -d .venv ]; then
  echo "Creating Python venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "Installing forge into venv..."
pip install --quiet --upgrade pip
pip install --quiet -e .
deactivate

# --- Forge moda client ---
if [ ! -d "${CLIENT_REPO}" ]; then
  echo "Cloning forge-moda-client..."
  git clone https://github.com/frmoded/forge-moda-client.git "${CLIENT_REPO}"
else
  echo "forge-moda-client: present at ${CLIENT_REPO}"
fi

cd "${CLIENT_APP}"
echo "Installing client npm deps (this can take a minute)..."
npm install --silent

# --- Done ---
cat <<'EOF'

=== Setup complete ===

Prerequisites, both repos, the Python venv and all deps are installed.

Forge no longer uses a local backend. Recipe generation runs through the
hosted forge-transpile service, and the Obsidian plugin is the primary UI --
there is nothing to start on this machine and no ANTHROPIC_API_KEY to export.
(The old ~/start-forge-backend.sh, ~/start-forge-client.sh and
~/update-forge.sh generators were removed 2026-08-12; if those files are still
sitting in your home directory from an earlier run of this script, they are
stale and can be deleted.)

Next steps (manual, one-time):

1. Install Obsidian if you haven't yet:
     https://obsidian.md

2. Install the Forge Client plugin into your vault:
     VAULT=~/path/to/your/vault bash ~/projects/forge-client-obsidian/scripts/install-latest.sh

3. Enable the "Forge Client" plugin in Settings -> Community Plugins.

4. Open an action note and click the run button. The plugin bundles its own
   engine and reaches forge-transpile for generation; no local server needed.

To move to head later:
  cd ~/projects/forge && git pull --ff-only && source .venv/bin/activate && pip install -e .

EOF
