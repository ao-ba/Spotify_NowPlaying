#!/usr/bin/env bash
set -e

# Run initial authentication if .spotifycache does not exist
if [ ! -f .spotifycache ]; then
  echo "No .spotifycache found. Starting initial authentication..."
  python -c "from server import init; init()"
fi

exec gunicorn -w 1 -b 0.0.0.0:5000 --timeout 30 server:app
