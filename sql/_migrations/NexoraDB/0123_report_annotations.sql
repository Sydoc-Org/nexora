-- 0123_report_annotations.sql
-- Chart annotations (#284): a report owner pins a short dated note on the
-- Simple-tab chart. BucketKey is the chart's own label string for the bucket
-- ('2026-09-01' for a month grain, the category value for a category axis).
-- Owner-gated in code (nx_lib/views/reporting/annotations.py); no permission
-- row. Idempotent.

IF OBJECT_ID(N'dbo.ReportAnnotations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportAnnotations (
        AnnotationID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportAnnotations PRIMARY KEY,
        ReportID     INT NOT NULL,
        BucketKey    NVARCHAR(64) NOT NULL,
        Text         NVARCHAR(500) NOT NULL,
        CreatedBy    INT NOT NULL,
        CreatedAt    DATETIME2(0) NOT NULL CONSTRAINT DF_ReportAnnotations_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ReportAnnotations_Reports FOREIGN KEY (ReportID)
            REFERENCES dbo.Reports(ReportID) ON DELETE CASCADE,
        CONSTRAINT FK_ReportAnnotations_Users FOREIGN KEY (CreatedBy)
            REFERENCES dbo.Users(userID)
    );
    CREATE INDEX IX_ReportAnnotations_Report ON dbo.ReportAnnotations(ReportID, BucketKey);
END;
GO
