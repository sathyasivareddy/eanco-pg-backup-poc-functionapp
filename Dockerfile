# Azure Functions Python base image (Debian bookworm based)
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true

# ---------------------------------------------------------------------------
# Install the PostgreSQL 18 client tools (provides pg_dump / pg_dumpall / psql)
# from the official PostgreSQL APT (PGDG) repository.
# ---------------------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg lsb-release && \
    install -d /usr/share/postgresql-common/pgdg && \
    curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc && \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client-18 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Make sure the PostgreSQL 18 binaries are on PATH
ENV PATH="/usr/lib/postgresql/18/bin:${PATH}"

# ---------------------------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------------------------
COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

# ---------------------------------------------------------------------------
# Copy the function app code
# ---------------------------------------------------------------------------
COPY . /home/site/wwwroot
