-- 0035_docfield_sensitive_and_validation_user.sql
-- Permission-gated doc-fields. Three idempotent changes:
--   1) New searchable doc-field column col_validationuser on dbo.SearchConfig.
--      (Its per-process source-column MAPPING is intentionally left NULL here --
--       set by the owner once the real source column/process is known; until
--       then the field never surfaces.)
--   2) IsSensitive flag on dbo.Search_Field_Labels + a 'validationuser' label
--      row flagged sensitive, with EN/DE/FR/IT labels (labels are DB-driven i18n).
--   3) The shared permission workitems.filter.documentfields.sensitive, granted
--      to every access profile that already grants admin.view (Effect 'A').

-- 1) SearchConfig: new field column (mapping stays NULL; owner maps it later).
IF COL_LENGTH('dbo.SearchConfig', 'col_validationuser') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_validationuser NVARCHAR(100) NULL;
GO

-- 2) Search_Field_Labels: sensitivity flag + the Validation User label row.
IF COL_LENGTH('dbo.Search_Field_Labels', 'IsSensitive') IS NULL
    ALTER TABLE dbo.Search_Field_Labels ADD IsSensitive BIT NOT NULL CONSTRAINT DF_Search_Field_Labels_IsSensitive DEFAULT(0);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Search_Field_Labels WHERE FieldKey = 'validationuser')
    INSERT INTO dbo.Search_Field_Labels (FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive)
    VALUES ('validationuser', 'Validation User', 'Prüfer', 'Validateur', 'Validatore', 1);
GO

-- Make sure the flag is set even if the row somehow pre-existed unflagged.
UPDATE dbo.Search_Field_Labels SET IsSensitive = 1 WHERE FieldKey = 'validationuser';
GO

-- 3) Permission + grant to admin.view profiles (0018 pattern).
INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.filter.documentfields.sensitive',
       'Workitems: view and search sensitive document fields (e.g. Validation User)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.filter.documentfields.sensitive');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.filter.documentfields.sensitive'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
