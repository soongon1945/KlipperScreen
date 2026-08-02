#!/bin/bash

# Wayland backends have their own compositor handoff.  The ready marker below
# is specifically produced by KlipperScreen-x11-client.sh after painting X.
if [[ "$BACKEND" =~ ^[wW]$ ]]; then
    exit 0
fi

READY_FILE="$XDG_RUNTIME_DIR/x11-handoff-ready"
for _ in {1..300}; do
    if [ -e "$READY_FILE" ]; then
        exit 0
    fi
    sleep 0.1
done

echo "Timed out waiting for the X11 splash handoff" >&2
exit 1
