CREATE PROCEDURE [dbo].[sp_TicketGen]
@SensorGroup NVARCHAR(50)
AS BEGIN

SET NOCOUNT ON
DECLARE @TicketGen TABLE(
    SecondsSinceLastEmailToday INT,
    DailyCount INT
)

INSERT INTO @TicketGen
SELECT
    DATEDIFF(SECOND, MAX([DateTime]), GETDATE()) AS SecondsSinceLastEmail,
    COUNT(*) AS DailyCount
FROM
    EmailLog
WHERE
    CAST([DateTime] AS DATE) = CAST(GETDATE() AS DATE)
    AND Sensorgroup = @SensorGroup;

IF (SELECT DailyCount from @TicketGen) = 0
(
    SELECT 1 AS 'TicketGen'
)
IF (SELECT @SensorGroup) IN ('doterr Files', 'Idle Time') AND (SELECT SecondsSinceLastEmailToday FROM @TicketGen) >= 3600
(
    SELECT 1 AS 'TicketGen'
)
ELSE(
    SELECT 0 AS 'TicketGen'
)
END;