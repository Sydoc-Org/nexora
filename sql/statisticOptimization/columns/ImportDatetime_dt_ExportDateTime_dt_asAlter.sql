ALTER TABLE PriveraPosteingang
ADD ImportDatetime_dt AS CONVERT(DATETIME, ImportDatetime, 104) PERSISTED;

ALTER TABLE PriveraPosteingang
ADD ExportDatetime_dt AS CONVERT(DATETIME, ExportDatetime, 104) PERSISTED;