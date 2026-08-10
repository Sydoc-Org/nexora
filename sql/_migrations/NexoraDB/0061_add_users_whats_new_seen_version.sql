-- What's New page (#169): per-user seen-marker for the header badge.
-- NULL = never opened the page; the app stamps its own version string on open.
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'whats_new_seen_version'
)
    ALTER TABLE dbo.Users ADD whats_new_seen_version NVARCHAR(32) NULL;
GO
