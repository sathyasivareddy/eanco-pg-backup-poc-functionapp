"""Timer-triggered Azure Function that backs up a PostgreSQL Flexible Server
(v18) database with pg_dump and uploads the dump to an Azure Storage account.

Backups are uploaded to blob storage using a Managed Identity (recommended) via
DefaultAzureCredential, or with a storage connection string if provided.
"""

import datetime
import logging
import os
import subprocess
import tempfile

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

app = func.FunctionApp()


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


def _run_pg_dump(dump_path: str) -> None:
    """Run pg_dump against the PostgreSQL Flexible Server."""
    host = _env("POSTGRES_HOST", required=True)
    port = _env("POSTGRES_PORT", "5432")
    database = _env("POSTGRES_DB", required=True)
    user = _env("POSTGRES_USER", required=True)
    password = _env("POSTGRES_PASSWORD", required=True)
    sslmode = _env("POSTGRES_SSLMODE", "require")

    # pg_dump reads the password from the PGPASSWORD env var so it never appears
    # on the command line / process list.
    dump_env = dict(os.environ)
    dump_env["PGPASSWORD"] = password
    dump_env["PGSSLMODE"] = sslmode

    cmd = [
        "pg_dump",
        "--host", host,
        "--port", str(port),
        "--username", user,
        "--dbname", database,
        "--format", "custom",  # compressed, restorable with pg_restore
        "--no-owner",
        "--no-privileges",
        "--verbose",
        "--file", dump_path,
    ]

    logging.info("Starting pg_dump for database '%s' on host '%s'.", database, host)
    result = subprocess.run(
        cmd,
        env=dump_env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logging.error("pg_dump stderr:\n%s", result.stderr)
        raise RuntimeError(f"pg_dump failed with exit code {result.returncode}.")

    logging.info("pg_dump completed successfully.")


def _upload_to_blob(local_path: str, blob_name: str) -> None:
    """Upload the dump file to Azure Blob Storage."""
    account_name = _env("STORAGE_ACCOUNT_NAME", required=True)
    container_name = _env("STORAGE_CONTAINER_NAME", "postgres-backups")
    connection_string = _env("STORAGE_CONNECTION_STRING")

    if connection_string:
        blob_service = BlobServiceClient.from_connection_string(connection_string)
    else:
        # Managed Identity / DefaultAzureCredential (recommended).
        account_url = f"https://{account_name}.blob.core.windows.net"
        credential = DefaultAzureCredential()
        blob_service = BlobServiceClient(account_url=account_url, credential=credential)

    container_client = blob_service.get_container_client(container_name)
    try:
        container_client.create_container()
        logging.info("Created container '%s'.", container_name)
    except Exception:  # noqa: BLE001 - container already exists is fine
        logging.info("Container '%s' already exists.", container_name)

    logging.info("Uploading '%s' to container '%s'.", blob_name, container_name)
    with open(local_path, "rb") as data:
        container_client.upload_blob(name=blob_name, data=data, overwrite=True)
    logging.info("Upload complete: %s", blob_name)


# Runs every day at 02:00 UTC. Override with the SCHEDULE app setting if needed.
@app.timer_trigger(
    schedule="%SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def backup_postgres(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("The timer is past due.")

    database = _env("POSTGRES_DB", "database")
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    blob_name = f"{database}/{database}-{timestamp}.dump"

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = os.path.join(tmp_dir, "backup.dump")
        _run_pg_dump(dump_path)
        _upload_to_blob(dump_path, blob_name)

    logging.info("PostgreSQL backup finished successfully: %s", blob_name)
