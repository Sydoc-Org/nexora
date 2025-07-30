WITH TopWorkItems AS (
    SELECT TOP 3
        WorkItemID
    FROM t_WorkItemAudits
    WHERE (CAST([TimeStamp] AS DATE) >= CAST(GETDATE() AS DATE))
      AND ([Action] = 'Released')
      AND (
           ActivityInstanceName LIKE '%C+A%'
        OR ActivityInstanceName LIKE '%Import%'
        OR ActivityInstanceName LIKE '%Email%'
        OR ActivityInstanceName LIKE '%OCR%'
        OR ActivityInstanceName LIKE '%Export%'
      )
    GROUP BY WorkItemID
    ORDER BY MAX([TimeStamp]) DESC
),
AuditStates AS (
    SELECT
        audits.WorkItemID,
        CASE
            WHEN audits.ActivityInstanceName LIKE '%Import%' OR audits.ActivityInstanceName LIKE '%Mail%' THEN 'Imported'
            WHEN audits.ActivityInstanceName LIKE '%OCR%' THEN 'In OCR'
            WHEN audits.ActivityInstanceName LIKE '%C+A%' THEN 'Validating'
            WHEN audits.ActivityInstanceName LIKE '%Export%' THEN 'In Export'
        END AS DisplayState
    FROM t_WorkItemAudits AS audits
    WHERE audits.WorkItemID IN (SELECT WorkItemID FROM TopWorkItems)
      AND (CAST(audits.[TimeStamp] AS DATE) >= CAST(GETDATE() AS DATE))
      AND (audits.[Action] = 'Released')
)
SELECT
    WorkItemID,
    MAX(CASE WHEN DisplayState = 'Imported' THEN 'True' ELSE 'False' END) AS Imported,
    MAX(CASE WHEN DisplayState = 'In OCR' THEN 'True' ELSE 'False' END) AS [In OCR],
    MAX(CASE WHEN DisplayState = 'Validating' THEN 'True' ELSE 'False' END) AS [In C+A],
    MAX(CASE WHEN DisplayState = 'In Export' THEN 'True' ELSE 'False' END) AS [In Export]
FROM AuditStates
GROUP BY WorkItemID
ORDER BY WorkItemID;


