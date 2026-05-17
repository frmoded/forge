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

# --- Write the daily startup script ---
cat > "${HOME}/start-forge-backend.sh" <<'EOF'
#!/usr/bin/env bash
# start-forge-backend.sh — start the Forge Python backend.
# Reads ANTHROPIC_API_KEY and FORGE_MODA_VAULT_PATH from environment.
#
# Usage:
#   export ANTHROPIC_API_KEY='your-key'
#   export FORGE_MODA_VAULT_PATH=/path/to/vault/forge-moda
#   bash ~/start-forge-backend.sh

set -euo pipefail

# Make sure brew-installed binaries are on PATH (non-interactive bash
# doesn't inherit the user's shell PATH).
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: ANTHROPIC_API_KEY not set."
  echo "Run: export ANTHROPIC_API_KEY='your-shared-key'"
  exit 1
fi

if [ -z "${FORGE_MODA_VAULT_PATH:-}" ]; then
  echo "WARNING: FORGE_MODA_VAULT_PATH not set."
  echo "  /moda/init will fail with 'snippet setup not found' until you set it."
  echo "  After installing forge-moda via the plugin, find where it landed:"
  echo "    find ~ -name setup.md -path '*forge-moda*'"
  echo "  Then: export FORGE_MODA_VAULT_PATH=/absolute/path/to/forge-moda"
fi

cd ~/projects/forge
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Starting backend on http://localhost:8000..."
echo "(In another terminal: cd ~/projects/forge-moda-client/forge-moda-web && npm run dev)"
exec uvicorn forge.api.server:app --reload --port 8000
EOF
chmod +x "${HOME}/start-forge-backend.sh"

cat > "${HOME}/start-forge-client.sh" <<'EOF'
#!/usr/bin/env bash
# start-forge-client.sh — start the Vite dev server for forge-moda-client.
# Usage: bash ~/start-forge-client.sh

set -euo pipefail

# Make sure brew-installed binaries (npm) are on PATH.
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

cd ~/projects/forge-moda-client/forge-moda-web
exec npm run dev
EOF
chmod +x "${HOME}/start-forge-client.sh"

cat > "${HOME}/update-forge.sh" <<'EOF'
#!/usr/bin/env bash
# update-forge.sh — pull latest backend + client from GitHub and reinstall deps.
# Run this when you want to move to head. Safe to re-run; no-ops if already up to date.
# Stop any running uvicorn / vite servers before running.
#
# Usage: bash ~/update-forge.sh

set -euo pipefail

# Make sure brew-installed binaries (npm) are on PATH.
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

echo "=== Updating Forge backend ==="
cd ~/projects/forge
git pull --ff-only
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e .
deactivate
echo "Backend up to date."

echo
echo "=== Updating Forge client ==="
cd ~/projects/forge-moda-client
git pull --ff-only
cd forge-moda-web
npm install --silent
echo "Client up to date."

echo
echo "=== Done ==="
echo "Restart the start-forge scripts to pick up the new versions."
EOF
chmod +x "${HOME}/update-forge.sh"

# --- Done ---
cat <<'EOF'

=== Setup complete ===

Three helper scripts written to your home directory:
  ~/start-forge-backend.sh   — starts uvicorn (needs API key + vault path)
  ~/start-forge-client.sh    — starts the Vite dev server
  ~/update-forge.sh          — pulls latest backend + client from GitHub
                                and reinstalls deps. Run before starting
                                if you want to move to head.

Next steps (manual, one-time):

1. Install Obsidian if you haven't yet:
     https://obsidian.md

2. Get your Anthropic API key from the project owner.

3. Start the backend in one terminal:
     export ANTHROPIC_API_KEY='<paste-key>'
     bash ~/start-forge-backend.sh

4. Start the client in a second terminal:
     bash ~/start-forge-client.sh

5. In Obsidian: install BRAT from Community Plugins, then in BRAT settings
   add this URL as a beta plugin:
     https://github.com/frmoded/forge-client-obsidian

6. Enable the "Forge Client" plugin in Settings → Community Plugins.

7. In a snippet, write the install call (English facet):
     Install version 0.1.9 of the forge-moda vault from the registry.
   Then Forge (Cmd+P → "Forge"). Wait for it to download the tarball.

8. Find where forge-moda landed (it goes inside your vault):
     find ~ -name setup.md -path '*forge-moda*'
   Stop the backend (Ctrl+C in its terminal). Re-export with the path:
     export FORGE_MODA_VAULT_PATH=/absolute/path/from/find/above
     bash ~/start-forge-backend.sh

9. In Obsidian: Cmd+P → "Forge: Open MoDa simulation". Particles should
   appear in the iframe.

Daily startup after the one-time setup above:
  Terminal 1:  export ANTHROPIC_API_KEY='...' && export FORGE_MODA_VAULT_PATH='...' && bash ~/start-forge-backend.sh
  Terminal 2:  bash ~/start-forge-client.sh
  Obsidian:    open the vault and use the plugin

To pull the latest backend + client from GitHub (do this when you want
to move to head; stop the start-forge servers first):
  bash ~/update-forge.sh

EOF
