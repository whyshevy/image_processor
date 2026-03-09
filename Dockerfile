FROM python:3.12-slim

# Detect architecture for MS ODBC repo
RUN ARCH=$(dpkg --print-architecture) && \
    echo "Building for architecture: $ARCH"

# Install ODBC Driver 18 for SQL Server (Linux) — supports amd64 & arm64
RUN apt-get update && \
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
    apt-get purge -y --auto-remove curl gnupg2 apt-transport-https gcc g++ && \
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
