#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [ -d "venv/bin" ]; then source venv/bin/activate
elif [ -d "venv/Scripts" ]; then source venv/Scripts/activate; fi
PYTHON=$(command -v python3 || command -v python)
if ! $PYTHON -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies..."
  $PYTHON -m pip install -r requirements.txt --quiet
fi
echo ""
echo "================================================"
echo "  FormIntellect Server"
echo "  Running at http://localhost:5000"
echo "  Press Ctrl+C to stop."
echo "================================================"
echo ""
$PYTHON -m server.main
