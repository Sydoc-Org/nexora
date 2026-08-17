-- The legacy "{SQL Server}" ODBC driver (default until finding 16's
-- DB_ODBC_DRIVER opt-in lands) returns DATETIME2 columns as Python str via
-- pyodbc instead of datetime, which broke the dbo.LoginLockout comparison
-- in auth.py (0062, #193 finding 7 -- live-tested and caught before this
-- shipped). DATETIME is fully native to the legacy driver and comes back
-- as a proper datetime object -- switch both timestamp columns.
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.LoginLockout') AND name = 'locked_until' AND system_type_id <> TYPE_ID('datetime')
)
    ALTER TABLE dbo.LoginLockout ALTER COLUMN locked_until DATETIME NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.LoginLockout') AND name = 'updated_at' AND system_type_id <> TYPE_ID('datetime')
)
BEGIN
    DECLARE @df NVARCHAR(200) = (
        SELECT dc.name FROM sys.default_constraints dc
        JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
        WHERE dc.parent_object_id = OBJECT_ID('dbo.LoginLockout') AND c.name = 'updated_at'
    );
    IF @df IS NOT NULL
        EXEC('ALTER TABLE dbo.LoginLockout DROP CONSTRAINT ' + @df);

    ALTER TABLE dbo.LoginLockout ALTER COLUMN updated_at DATETIME NOT NULL;
    ALTER TABLE dbo.LoginLockout ADD CONSTRAINT DF_LoginLockout_updated_at DEFAULT (GETUTCDATE()) FOR updated_at;
END
GO
