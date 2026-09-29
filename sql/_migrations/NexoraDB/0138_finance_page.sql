-- 0138_finance_page.sql  (#408)
-- The Sydoc Finance page: the monthly accounting figures of every billed
-- client on one page per month (/finance), read from the same registry rows
-- Reporting uses (dbo.ReportingSources / dbo.ReportingMetrics, 0124-0137).
--
-- ONE CODE GATES THE WHOLE PAGE
-- finance.view is a new area (docs/design/permissions.md). The page reads
-- every registered billing source through the generic 'table' provider,
-- which applies no row scoping, so this code is the entire gate between
-- one customer's figures and another's. It is for Sydoc's own accounting
-- and must never be granted to a customer profile -- the same rule as the
-- reporting.source.<code>.use codes of the sources it reads (0136).
--
-- Global Admin gets it here, for the same reason 0136 had to grant the six
-- billing sources: that profile carries a hand-picked subset, so a new code
-- is invisible to it until a migration says otherwise. Enterprise Admin
-- picks it up through the 0106 trigger. Nobody else.
--
-- ONE MORE MEASURE ON THE BPS SOURCE
-- The page's "Sydoc services" section shows the hours booked in the BPS
-- timetool per task and per customer (0124's dbo.BPS_ProjectReport). 0124
-- registered total hours and absence hours (Kunde = 'Absences': vacation,
-- sick leave, ...); what accounting reads off a month is the complement --
-- hours on real customers -- so that is registered as its own measure
-- rather than subtracted by hand. Same conditional-aggregate pattern as
-- 0124's absence measure, inverted.
--
-- Idempotent and self-limiting: no rows if the profile or the code is absent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'finance.view', N'View the Sydoc Finance page (monthly accounting figures of every billed client)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'finance.view');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name = N'Global Admin'
  AND p.Code = N'finance.view'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID
  );
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('bps_projects_service_hours', 'bps_projects',
        N'Service hours', N'Leistungsstunden', N'Heures de prestation', N'Ore di prestazione',
        'sum', 'Stunden', N'[{"field":"Kunde","op":"ne","value":"Absences"}]',
        N'Hours booked on real customers and internal work -- everything except the Absences pseudo-customer (vacation, sick leave, compensation). The complement of Absence hours.', NULL, 123)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
