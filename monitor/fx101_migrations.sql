-- SQLite schema is applied idempotently by monitor.fx101.db().
-- Kept separately for deployment/audit tooling.
CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, source TEXT NOT NULL, scanned_at TEXT NOT NULL, result TEXT NOT NULL, payload TEXT NOT NULL);
