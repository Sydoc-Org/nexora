use nexora
DECLARE @i int = 1
DECLARE @usercount int
DECLARE @usermapping TABLE(
    idx int IDENTITY(1,1),
    userid int
)
SELECT @usercount = count(*) from users
DECLARE @currentUser int

INSERT INTO @usermapping
SELECT userid from users

WHILE @i <= @usercount
BEGIN
    SELECT @currentUser = userid from @usermapping WHERE idx = @i
    INSERT INTO Notifications(UserID, [Message], Icon)
    VALUES(@currentUser, 'Nexora will not be available during 00:00 and 01:00 Tommorow', 'fa-power-off')
    SET @i = @i + 1
END