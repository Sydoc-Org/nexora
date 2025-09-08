USE RuntimeDatabase;

WITH
    CTE
    AS
    (
        SELECT a.WorkItemID, a.[TimeStamp] ,
            ROW_NUMBER() OVER (PARTITION BY a.WorkItemID ORDER BY  a.[TimeStamp]  DESC) rn
        FROM t_WorkItemAudits a
            RIGHT JOIN t_WorkItems w on a.WorkItemID = w.ID
            RIGHT JOIN t_ActivityInstances ai on ai.ID = w.ActivityInstanceID
            LEFT JOIN t_Processes p ON p.ID = ai.ProcessID
        WHERE p.Name = '01_Invoice_SAP'
    )
SELECT top 3
    WorkItemID
FROM CTE
WHERE rn = 1
ORDER BY [TimeStamp] DESC
