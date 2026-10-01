-- 0147_controlling_close_and_rates_edit.sql  (#433)
-- From the Controlling design review:
--
-- 1. controlling.rates.edit -- edits the rates and external costs of the
--    Controlling page (dbo.FinanceRates, dbo.ControllingCosts). Global Admin,
--    like controlling.view; Enterprise Admin through the 0106 trigger. Until
--    now the page borrowed finance.month.edit.
-- 2. dbo.ControllingMonthClose -- the Controlling figures of a month, frozen
--    when Sydoc Finance closes that month (one JSON payload per month: every
--    stream's hours, rate, cost, invoiced amounts, margin and documents).
--    Reopening the month in Finance deletes the row with Finance's own
--    snapshot. Bexio lines stay live; the page shows where they moved.
--
-- Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'controlling.rates.edit', N'Edit the rates and external costs of the Sydoc Controlling page'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'controlling.rates.edit');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name = N'Global Admin'
  AND p.Code = N'controlling.rates.edit'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID
  );
GO

IF OBJECT_ID(N'dbo.ControllingMonthClose', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ControllingMonthClose (
        Month    CHAR(7)       NOT NULL,
        Payload  NVARCHAR(MAX) NOT NULL,
        ClosedAt DATETIME2(0)  NOT NULL CONSTRAINT DF_ControllingMonthClose_ClosedAt DEFAULT SYSUTCDATETIME(),
        ClosedBy NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_ControllingMonthClose PRIMARY KEY (Month),
        CONSTRAINT CK_ControllingMonthClose_Payload CHECK (ISJSON(Payload) = 1)
    );
END;
GO
