ALTER TABLE PriveraInitialUndNeuzugaenge
ADD ImportDatetime_dt AS CONVERT(DATETIME, Scandate, 104) PERSISTED;