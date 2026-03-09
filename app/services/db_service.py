"""Database service — MS SQL Server connection and InProgressMedia table operations."""

import glob
import logging
import os

import pyodbc

logger = logging.getLogger(__name__)

_resolved_driver: str | None = None


def _resolve_driver(configured: str) -> str:
    """Return a working ODBC driver string.

    If the configured driver name (e.g. 'ODBC Driver 18 for SQL Server') works,
    return it as-is.  Otherwise, locate the .so file on disk and return its
    absolute path so pyodbc can load it directly.
    """
    global _resolved_driver
    if _resolved_driver is not None:
        return _resolved_driver

    # Check if configured name is already resolvable via odbcinst
    available = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if configured in available:
        _resolved_driver = configured
        return _resolved_driver

    # Fallback: find the .so file directly
    so_files = sorted(glob.glob("/opt/microsoft/**/libmsodbcsql*.so.*", recursive=True))
    if so_files:
        logger.warning("Configured driver '%s' not found in pyodbc.drivers(); "
                        "using .so path: %s", configured, so_files[0])
        _resolved_driver = so_files[0]
        return _resolved_driver

    # Last resort — return configured name and let pyodbc raise a clear error
    logger.error("No ODBC driver found. Available drivers: %s", pyodbc.drivers())
    _resolved_driver = configured
    return _resolved_driver


def get_connection(config: dict) -> pyodbc.Connection:
    """Create a connection to MS SQL Server using config dict."""
    driver = _resolve_driver(config['DB_DRIVER'])
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={config['DB_SERVER']};"
        f"DATABASE={config['DB_NAME']};"
        f"UID={config['DB_USER']};"
        f"PWD={config['DB_PASSWORD']};"
        f"TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


def ensure_table(config: dict) -> None:
    """Create [dbo].[InProgressMedia] and [dbo].[MediaCounter] tables if they don't exist."""
    ddl_main = """
    IF NOT EXISTS (
        SELECT * FROM sys.objects
        WHERE object_id = OBJECT_ID(N'[dbo].[InProgressMedia]') AND type = 'U'
    )
    BEGIN
        CREATE TABLE [dbo].[InProgressMedia] (
            [id]                    INT IDENTITY(1,1) NOT NULL,
            [FileName]              NVARCHAR(500)      NULL,
            [FolderPath]            NVARCHAR(MAX)      NULL,
            [FullName]              NVARCHAR(MAX)      NULL,
            [Extention]             NVARCHAR(20)       NULL,
            [Size]                  NVARCHAR(50)       NULL,
            [DateCreated]           DATETIME           NULL,
            [DateModified]          DATETIME           NULL,
            [IsProcessed]           BIT                NULL,
            [MediaId]               INT                NULL,
            [UniqueMediaId]         INT                NULL,
            [AIDescription]         NVARCHAR(MAX)      NULL,
            [UKR_Keywords]          NVARCHAR(MAX)      NULL,
            [EN_Keywords]           NVARCHAR(MAX)      NULL,
            [OriginalFullPath]      NVARCHAR(MAX)      NULL,
            [OriginalFileName]      NVARCHAR(MAX)      NULL,
            [OriginalExtension]     NVARCHAR(20)       NULL,
            [OriginalFileSizeBytes] INT                NULL,
            [OriginalWidthPx]       INT                NULL,
            [OriginalHeightPx]      INT                NULL,
            [OriginalPixelCount]    INT                NULL,
            [OriginalAspectRatio]   DECIMAL(18, 0)     NULL,
            [OriginalPILFormat]     NVARCHAR(20)       NULL,
            [OriginalMagicType]     NVARCHAR(20)       NULL,
            [OriginalModifiedTime]  DATETIME           NULL,
            [OriginalMD5]           NVARCHAR(200)      NULL,
            [OriginalSHA1]          NVARCHAR(200)      NULL,
            [DimSource]             NVARCHAR(20)       NULL,
            [ProcessedFileName]     NVARCHAR(MAX)      NULL,
            [ProcessedFilePath]     NVARCHAR(MAX)      NULL,
            PRIMARY KEY CLUSTERED ([id] ASC)
        );
    END
    """

    ddl_counter = """
    IF NOT EXISTS (
        SELECT * FROM sys.objects
        WHERE object_id = OBJECT_ID(N'[dbo].[MediaCounter]') AND type = 'U'
    )
    BEGIN
        CREATE TABLE [dbo].[MediaCounter] (
            [id]              INT IDENTITY(1,1) NOT NULL,
            [MediaId]         INT                NULL,
            [FolderPath]      NVARCHAR(MAX)      NULL,
            [FileName]        NVARCHAR(500)      NULL,
            [ProcessingData]  DATETIME           NULL DEFAULT GETDATE(),
            PRIMARY KEY CLUSTERED ([id] ASC)
        );
    END
    """

    conn = get_connection(config)
    try:
        conn.execute(ddl_main)
        conn.execute(ddl_counter)
        conn.commit()
    finally:
        conn.close()


def _bytes_to_mb(val: str) -> str | None:
    """Convert bytes string to MB string with 2 decimal places."""
    try:
        b = int(val) if val else None
        if b is None:
            return None
        return f"{b / (1024 * 1024):.2f} MB"
    except (ValueError, TypeError):
        return None


def _safe_int(val: str) -> int | None:
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None


def _safe_decimal(val: str) -> float | None:
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def _get_next_media_id(conn: pyodbc.Connection) -> int:
    """Return MAX(MediaId) + 1 from MediaCounter (the master source). Starts from 1 if empty."""
    sql = "SELECT ISNULL(MAX([MediaId]), 0) + 1 FROM [dbo].[MediaCounter]"
    cursor = conn.execute(sql)
    return cursor.fetchone()[0]


def _insert_media_counter(conn: pyodbc.Connection, media_id: int, folder_path: str, file_name: str) -> None:
    """Insert a record into [dbo].[MediaCounter]."""
    sql = """
    INSERT INTO [dbo].[MediaCounter] ([MediaId], [FolderPath], [FileName], [ProcessingData])
    VALUES (?, ?, ?, GETDATE())
    """
    conn.execute(sql, (media_id, folder_path, file_name))


def insert_processed_media(
    config: dict,
    job_id: str,
    proc_jpeg_name: str,
    proc_jpeg_path: str,
    preprops: dict[str, str],
    description: str,
    uk_pipe: str,
    en_pipe: str,
    orig_path: str,
) -> None:
    """Insert one processed image record into [dbo].[InProgressMedia] and [dbo].[MediaCounter]."""
    sql = """
    INSERT INTO [dbo].[InProgressMedia] (
        [FileName], [FolderPath], [FullName], [Extention], [Size],
        [DateCreated], [DateModified], [IsProcessed], [MediaId],
        [AIDescription], [UKR_Keywords], [EN_Keywords],
        [OriginalFullPath], [OriginalFileName], [OriginalExtension],
        [OriginalFileSizeBytes], [OriginalWidthPx], [OriginalHeightPx],
        [OriginalPixelCount], [OriginalAspectRatio],
        [OriginalPILFormat], [OriginalMagicType], [OriginalModifiedTime],
        [OriginalMD5], [OriginalSHA1], [DimSource],
        [ProcessedFileName], [ProcessedFilePath]
    ) VALUES (
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?,
        ?, ?,
        ?, ?, ?,
        ?, ?, ?,
        ?, ?
    )
    """

    original_filename = preprops.get("OriginalFileName", os.path.basename(orig_path))
    folder_path = os.path.dirname(orig_path)
    ext = preprops.get("OriginalExtension", "")
    size_mb = _bytes_to_mb(preprops.get("OriginalFileSizeBytes", ""))
    modified_time = preprops.get("OriginalModifiedTime", "") or None

    conn = get_connection(config)
    try:
        next_media_id = _get_next_media_id(conn)

        params = (
            original_filename,                                  # FileName
            folder_path,                                        # FolderPath
            orig_path,                                          # FullName
            ext,                                                # Extention
            size_mb,                                            # Size (MB)
            modified_time,                                      # DateCreated
            modified_time,                                      # DateModified
            True,                                               # IsProcessed
            next_media_id,                                      # MediaId
            description,                                        # AIDescription
            uk_pipe,                                            # UKR_Keywords
            en_pipe,                                            # EN_Keywords
            preprops.get("OriginalFullPath", orig_path),        # OriginalFullPath
            original_filename,                                  # OriginalFileName
            ext,                                                # OriginalExtension
            _safe_int(preprops.get("OriginalFileSizeBytes")),   # OriginalFileSizeBytes
            _safe_int(preprops.get("OriginalWidthPx")),         # OriginalWidthPx
            _safe_int(preprops.get("OriginalHeightPx")),        # OriginalHeightPx
            _safe_int(preprops.get("OriginalPixelCount")),      # OriginalPixelCount
            _safe_decimal(preprops.get("OriginalAspectRatio")), # OriginalAspectRatio
            preprops.get("OriginalPILFormat", ""),              # OriginalPILFormat
            preprops.get("OriginalMagicType", ""),              # OriginalMagicType
            modified_time,                                      # OriginalModifiedTime
            preprops.get("OriginalMD5", ""),                    # OriginalMD5
            preprops.get("OriginalSHA1", ""),                   # OriginalSHA1
            preprops.get("DimSource", ""),                      # DimSource
            proc_jpeg_name,                                     # ProcessedFileName
            proc_jpeg_path,                                     # ProcessedFilePath
        )

        conn.execute(sql, params)

        # Also insert into MediaCounter
        _insert_media_counter(conn, next_media_id, folder_path, original_filename)

        conn.commit()
    finally:
        conn.close()


def get_records_by_job(config: dict, job_id: str) -> list[dict]:
    """Fetch latest InProgressMedia records."""
    sql = """
    SELECT TOP 500
        [id], [FileName], [FolderPath], [FullName], [Extention], [Size],
        [DateCreated], [DateModified], [IsProcessed],
        [MediaId], [UniqueMediaId],
        [AIDescription], [UKR_Keywords], [EN_Keywords],
        [OriginalFullPath], [OriginalFileName], [OriginalExtension],
        [OriginalFileSizeBytes], [OriginalWidthPx], [OriginalHeightPx],
        [OriginalPixelCount], [OriginalAspectRatio],
        [OriginalPILFormat], [OriginalMagicType], [OriginalModifiedTime],
        [OriginalMD5], [OriginalSHA1], [DimSource],
        [ProcessedFileName], [ProcessedFilePath]
    FROM [dbo].[InProgressMedia]
    ORDER BY [id] DESC
    """
    conn = get_connection(config)
    try:
        cursor = conn.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append(dict(zip(columns, [str(v) if v is not None else "" for v in row])))
        return rows
    finally:
        conn.close()


def get_all_records(config: dict, limit: int = 500) -> list[dict]:
    """Fetch the latest records from InProgressMedia."""
    sql = f"""
    SELECT TOP {limit}
        [id], [FileName], [FolderPath], [FullName], [Extention], [Size],
        [DateCreated], [DateModified], [IsProcessed],
        [MediaId], [UniqueMediaId],
        [AIDescription], [UKR_Keywords], [EN_Keywords],
        [OriginalFullPath], [OriginalFileName], [OriginalExtension],
        [OriginalFileSizeBytes], [OriginalWidthPx], [OriginalHeightPx],
        [OriginalPixelCount], [OriginalAspectRatio],
        [OriginalPILFormat], [OriginalMagicType], [OriginalModifiedTime],
        [OriginalMD5], [OriginalSHA1], [DimSource],
        [ProcessedFileName], [ProcessedFilePath]
    FROM [dbo].[InProgressMedia]
    ORDER BY [id] DESC
    """
    conn = get_connection(config)
    try:
        cursor = conn.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append(dict(zip(columns, [str(v) if v is not None else "" for v in row])))
        return rows
    finally:
        conn.close()


def check_already_processed(config: dict, md5: str) -> bool:
    """Check if an image with this MD5 hash was already processed."""
    sql = "SELECT COUNT(*) FROM [dbo].[InProgressMedia] WHERE [OriginalMD5] = ?"
    conn = get_connection(config)
    try:
        cursor = conn.execute(sql, (md5,))
        count = cursor.fetchone()[0]
        return count > 0
    finally:
        conn.close()
