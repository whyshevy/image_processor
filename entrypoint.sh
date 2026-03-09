#!/bin/bash
# Entrypoint: verify ODBC driver .so path before starting the app.

ODBCINST="/etc/odbcinst.ini"

if [ -f "$ODBCINST" ]; then
    # Read the Driver= path currently configured
    CONFIGURED=$(grep -oP '^Driver\s*=\s*\K.*' "$ODBCINST" | head -1)

    if [ -n "$CONFIGURED" ] && [ ! -f "$CONFIGURED" ]; then
        echo "[entrypoint] ODBC driver not found at configured path: $CONFIGURED"

        # Try to locate the real .so file
        ACTUAL=$(find /opt/microsoft/ -name "libmsodbcsql*.so.*" -type f 2>/dev/null | head -1)

        if [ -n "$ACTUAL" ]; then
            echo "[entrypoint] Found driver at: $ACTUAL — updating $ODBCINST"
            sed -i "s|^Driver\s*=.*|Driver=$ACTUAL|" "$ODBCINST"
        else
            echo "[entrypoint] WARNING: No ODBC driver .so found under /opt/microsoft/"
        fi
    else
        echo "[entrypoint] ODBC driver OK: $CONFIGURED"
    fi
fi

# Execute the main command (passed as CMD from Dockerfile)
exec "$@"
