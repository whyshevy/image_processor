import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=100.119.20.23,1433;"
    "UID=SA;"
    "PWD=nP2ks4!00b;"
    "TrustServerCertificate=yes;",
    timeout=15,
    autocommit=True,
)

conn.execute("IF DB_ID('ProcessedMedia') IS NULL CREATE DATABASE [ProcessedMedia]")
print("Database [ProcessedMedia] ready!")

# Verify
cursor = conn.execute("SELECT name FROM sys.databases WHERE name = 'ProcessedMedia'")
row = cursor.fetchone()
print(f"Confirmed: {row[0]}" if row else "ERROR: DB not found")

conn.close()
