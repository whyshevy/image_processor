FROM python:3.12-slim

# Install ODBC Driver 18 for SQL Server (Linux)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl gnupg2 apt-transport-https unixodbc-dev gcc g++ && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    # Verify driver installed and show actual .so file
    find /opt/microsoft/ -name "libmsodbcsql*" -type f 2>/dev/null && \
    # Update odbcinst.ini to point to the actual .so file found on disk
    ACTUAL_SO=$(find /opt/microsoft/ -name "libmsodbcsql*.so.*" -type f | head -1) && \
    if [ -n "$ACTUAL_SO" ]; then \
        echo "Found ODBC driver: $ACTUAL_SO"; \
        sed -i "s|Driver=.*|Driver=$ACTUAL_SO|" /etc/odbcinst.ini; \
    fi && \
    cat /etc/odbcinst.ini && \
    apt-get purge -y --auto-remove curl gnupg2 apt-transport-https gcc g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Create runtime directories
RUN mkdir -p uploads processed

EXPOSE 5000 5050

CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "--threads", "4", "--timeout", "300", "run:app"]
