SELECT tat.Name, ROW_NUMBER() OVER (ORDER BY AuditNumber) Step FROM t_WorkItemAudits twia 
RIGHT JOIN t_ActivityInstances tai ON twia.ActivityInstanceID = tai.ID  
RIGHT JOIN t_ActivityTypes tat ON tat.ID = tai.ActivityTypeID 
WHERE twia.WorkItemID = 504764 AND Action = 'Released'
order by twia.AuditNumber 
