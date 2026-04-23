#!/bin/bash
set -e

# Start Xvfb
export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!

# Wait for Xvfb to be ready
for i in $(seq 1 10); do
    if xdpyinfo -display :99 >/dev/null 2>&1; then
        echo "[entrypoint] Xvfb ready (PID=$XVFB_PID)"
        break
    fi
    sleep 0.5
done

# Run the registration script with all CLI args
echo "[entrypoint] Starting: python3 DrissionPage_example.py $@"
python3 DrissionPage_example.py "$@"
EXIT_CODE=$?

# Cleanup
kill $XVFB_PID 2>/dev/null || true
exit $EXIT_CODE
