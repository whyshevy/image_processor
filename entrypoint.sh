#!/bin/bash
# Entrypoint: verify ODBC driver .so path before starting the app.

ODBCINST="/etc/odbcinst.ini"

echo "[entrypoint] Checking ODBC driver..."

# Find the actual .so file on disk
ACTUAL=$(find /opt/microsoft/ -name "libmsodbcsql*.so.*" -type f 2>/dev/null | head -1)

if [ -n "$ACTUAL" ]; then
    echo "[entrypoint] Found ODBC driver: $ACTUAL"

    # Always overwrite odbcinst.ini to ensure it points to the real file
    if [ -f "$ODBCINST" ]; then
        sed -i "s|^Driver[[:space:]]*=.*|Driver=$ACTUAL|" "$ODBCINST"
        echo "[entrypoint] Updated $ODBCINST:"
        cat "$ODBCINST"
    fi
else
    echo "[entrypoint] WARNING: No ODBC driver .so found under /opt/microsoft/"
    echo "[entrypoint] Contents of /opt/microsoft/:"
    find /opt/microsoft/ -type f 2>/dev/null || echo "  (directory not found)"
fi

# Execute the main command (passed as CMD from Dockerfile)
exec "$@"
