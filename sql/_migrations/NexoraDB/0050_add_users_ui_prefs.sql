-- Per-user UI preferences (theme, accent, motion, entrance, density, sidebar)
-- stored as a small JSON blob. Read once per session into session['ui_prefs']
-- (same idiom as Users.locale). Issue #155.
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'ui_prefs'
)
BEGIN
    ALTER TABLE dbo.Users ADD ui_prefs NVARCHAR(500) NULL;
END
GO
