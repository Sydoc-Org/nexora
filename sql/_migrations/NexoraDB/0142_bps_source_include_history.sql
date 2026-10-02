-- 0142_bps_source_include_history.sql  (#424)
-- The bpsuite Projektbericht feed (SYDOC_Statistik.dbo.BPS_ProjectReport) is
-- truncated and reloaded at 04:00 and starts on 2026-08-03, so older bookings
-- cannot live in it. They were loaded once from an older export into
-- SYDOC_Statistik.dbo.BPS_ProjectReportHistory, and
-- SYDOC_Statistik.dbo.BPS_ProjectReportAll = feed UNION ALL history (history
-- only below the feed's first date, so a widened export never double-counts).
-- Both objects live on the vendor-side Statistics DB (not tracked under sql/);
-- see docs/howto/bps.md. Repoint the bps_projects source (0124) at the view --
-- same columns -- so /bps, Reporting and Finance all see the history.
-- Idempotent.

UPDATE dbo.ReportingSources
SET BaseObject = 'dbo.BPS_ProjectReportAll'
WHERE Code = 'bps_projects' AND BaseObject = 'dbo.BPS_ProjectReport';
GO
