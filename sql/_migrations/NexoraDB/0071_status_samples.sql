-- 0071: latency samples behind the /admin/status sparklines.
--
-- The outage monitor already measures how long every probe took ("158 ms" in
-- StatusComponents.Detail) and then throws it away, so the status page can say
-- "operational" but never "operational, and three times slower than yesterday".
-- One narrow row per component per run keeps a short trend without turning the
-- monitor into a metrics system: at a 5-minute cadence, 14 days of retention is
-- ~4k rows per component.
IF OBJECT_ID('dbo.StatusSamples', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.StatusSamples (
        ComponentKey NVARCHAR(200)  NOT NULL,
        SampledAt    DATETIME2(0)   NOT NULL,
        LatencyMs    INT            NOT NULL,
        Ok           BIT            NOT NULL CONSTRAINT DF_StatusSamples_Ok DEFAULT (1),
        CONSTRAINT PK_StatusSamples PRIMARY KEY CLUSTERED (ComponentKey ASC, SampledAt ASC)
    );
END
GO

-- The page reads "every sample newer than X", across components, and the
-- monitor deletes by age. The clustered PK leads with ComponentKey, so neither
-- is a seek without this.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_StatusSamples_SampledAt'
               AND object_id = OBJECT_ID('dbo.StatusSamples'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_StatusSamples_SampledAt
        ON dbo.StatusSamples (SampledAt ASC) INCLUDE (ComponentKey, LatencyMs, Ok);
END
GO
