#!/bin/bash

# Xorg replaces Plymouth's retained framebuffer before GTK finishes loading.
# Paint the same final frame on the X root window so users do not see a black
# transition while KlipperScreen imports Python modules and creates its window.
if command -v xsetroot >/dev/null 2>&1; then
    /usr/bin/xsetroot -solid "#ffffff" 2>/dev/null || true
fi

SPLASH_IMAGE="${KS_X11_SPLASH_IMAGE:-/usr/share/plymouth/themes/makerpi/progress-91.png}"
if command -v feh >/dev/null 2>&1 && [ -r "$SPLASH_IMAGE" ]; then
    /usr/bin/feh \
        --no-fehbg \
        --bg-center \
        --image-bg "#ffffff" \
        "$SPLASH_IMAGE" || true
fi

exec $KS_XCLIENT
