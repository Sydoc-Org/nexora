-- One-time data migration: the app's accent default is changing from indigo
-- ("Classic") to amber. Users currently on indigo -- either they never
-- touched the appearance picker at all, or they explicitly chose indigo --
-- move to the new amber default. Anyone on any other explicit accent
-- (violet, emerald, amber already, rose, sky, custom) is untouched.
-- Theme is left alone except: rows with no theme preference stored at all
-- get an explicit 'light' (already the effective default for them, just
-- making it durable); explicit dark-mode users keep dark.
-- Idempotent: after the first run, matching rows carry accent='amber' and
-- no longer match the WHERE clause below.
;WITH base AS (
    SELECT
        userid,
        CASE WHEN ui_prefs IS NOT NULL AND ISJSON(ui_prefs) = 1
             THEN ui_prefs ELSE '{}' END AS prefs
    FROM dbo.Users
),
target AS (
    SELECT userid, prefs
    FROM base
    WHERE JSON_VALUE(prefs, '$.accent') IS NULL
       OR JSON_VALUE(prefs, '$.accent') = 'indigo'
)
UPDATE u
SET ui_prefs = JSON_MODIFY(
        CASE WHEN JSON_VALUE(t.prefs, '$.theme') IS NULL
             THEN JSON_MODIFY(t.prefs, '$.theme', 'light')
             ELSE t.prefs END,
        '$.accent', 'amber')
FROM dbo.Users u
JOIN target t ON t.userid = u.userid;
GO
