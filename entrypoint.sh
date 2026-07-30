#!/usr/bin/env bash
set -e

echo "Starting Spotify NowPlaying Dashboard server..."
exec gunicorn -w 1 -b 0.0.0.0:5000 --timeout 30 server:app
