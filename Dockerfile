FROM python:3.12-slim

# Detect architecture for MS ODBC repo
RUN ARCH=$(dpkg --print-architecture) && \
    echo "Building for architecture: $ARCH"

# Install ODBC Driver 18 for SQL Server (Linux) — supports amd64 & arm64
# Step 1: Install build-time AND runtime dependencies separately
RUN apt-get update && \
    # Runtime deps that must stay: unixodbc, Kerberos, OpenSSL
    apt-get install -y --no-install-recommends \
        unixodbc libgssapi-krb5-2 libltdl7 && \
    # Build-time deps (will be removed later)
    apt-get install -y --no-install-recommends \
        curl gnupg2 apt-transport-https unixodbc-dev gcc g++ && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    ARCH=$(dpkg --print-architecture) && \
    echo "deb [arch=${ARCH} signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    # Verify driver installed and show actual .so file
    echo "=== Installed ODBC driver files ===" && \
    find /opt/microsoft/ -name "libmsodbcsql*" -type f 2>/dev/null && \
    # Update odbcinst.ini to point to the actual .so file found on disk
    ACTUAL_SO=$(find /opt/microsoft/ -name "libmsodbcsql*.so.*" -type f | head -1) && \
    if [ -n "$ACTUAL_SO" ]; then \
        echo "Found ODBC driver: $ACTUAL_SO"; \
        sed -i "s|^Driver[[:space:]]*=.*|Driver=$ACTUAL_SO|" /etc/odbcinst.ini; \
    else \
        echo "ERROR: No ODBC .so file found!" && exit 1; \
    fi && \
    echo "=== odbcinst.ini ===" && cat /etc/odbcinst.ini && \
    # Verify the driver can be loaded (check shared lib dependencies)
    echo "=== ldd check ===" && ldd "$ACTUAL_SO" && \
    # Remove only build-time deps (NOT --auto-remove, to keep runtime libs)
    apt-get purge -y curl gnupg2 apt-transport-https gcc g++ unixodbc-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Create runtime directories
RUN mkdir -p uploads processed

# Entrypoint verifies ODBC driver path at runtime
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000 5050

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "--threads", "4", "--timeout", "300", "run:app"]
