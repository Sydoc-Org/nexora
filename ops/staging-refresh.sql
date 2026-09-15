-- nexora staging refresh (#338): copy the two app-owned PROD databases to
-- *_STAGING every night at 01:00, on the same server. COPY_ONLY leaves the real
-- backup chain (sqlBackuper.ps1 -> Azure) untouched. The 01:30 GitHub Actions
-- schedule then redeploys main to staging and re-applies pending migrations.
--
-- Install once (re-running reinstalls the job), as sysadmin:
--   sqlcmd -S PRDSQL01\PRDSQL01 -U <DB_UID> -P <DB_PWD> -b -i ops/staging-refresh.sql
-- Run it now:
--   EXEC msdb.dbo.sp_start_job N'nexora - staging refresh';
--
-- The step is one N'...' literal: every quote inside it is doubled.
USE msdb;
GO
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'nexora - staging refresh')
    EXEC msdb.dbo.sp_delete_job @job_name = N'nexora - staging refresh';
GO
EXEC msdb.dbo.sp_add_job
    @job_name = N'nexora - staging refresh',
    @description = N'nexora #338: COPY_ONLY backup of nexora + Generali, restore as *_STAGING. Runs before the 01:30 staging redeploy in GitHub Actions. Source: ops/staging-refresh.sql in the nexora repo.';
GO
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'nexora - staging refresh',
    @step_name = N'refresh',
    @subsystem = N'TSQL',
    @database_name = N'master',
    @on_success_action = 1,  -- quit reporting success
    @on_fail_action = 2,     -- quit reporting failure
    @command = N'
SET NOCOUNT ON;
EXEC master.sys.xp_create_subdir N''D:\tmp\staging'';

DECLARE @pairs TABLE (src sysname, dst sysname);
INSERT @pairs VALUES (N''nexora'', N''nexora_STAGING''), (N''Generali'', N''Generali_STAGING'');

DECLARE @src sysname, @dst sysname, @bak nvarchar(260), @sql nvarchar(max), @move nvarchar(max);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT src, dst FROM @pairs;
OPEN c;
FETCH NEXT FROM c INTO @src, @dst;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @bak = N''D:\tmp\staging\'' + @src + N''.bak'';

    SET @sql = N''BACKUP DATABASE '' + QUOTENAME(@src) + N'' TO DISK = @bak WITH COPY_ONLY, INIT, COMPRESSION, CHECKSUM;'';
    EXEC sp_executesql @sql, N''@bak nvarchar(260)'', @bak = @bak;

    -- MOVE every file of the source to a *_STAGING file name. Same server, so
    -- the source''s logical names ARE the backup''s -- no FILELISTONLY needed.
    SELECT @move = STRING_AGG(CAST(
        N''MOVE N'''''' + name + N'''''' TO N''''''
        + CASE type_desc WHEN N''LOG'' THEN N''D:\log\'' ELSE N''D:\data\'' END
        + @dst + N''_'' + CAST(file_id AS nvarchar(3))
        + CASE type_desc WHEN N''LOG'' THEN N''.ldf'' ELSE N''.mdf'' END
        + N'''''''' AS nvarchar(max)), N'', '')
    FROM sys.master_files WHERE database_id = DB_ID(@src);

    IF DB_ID(@dst) IS NOT NULL
    BEGIN
        SET @sql = N''ALTER DATABASE '' + QUOTENAME(@dst) + N'' SET SINGLE_USER WITH ROLLBACK IMMEDIATE;'';
        EXEC sp_executesql @sql;
    END

    SET @sql = N''RESTORE DATABASE '' + QUOTENAME(@dst) + N'' FROM DISK = @bak WITH REPLACE, RECOVERY, CHECKSUM, '' + @move + N'';'';
    EXEC sp_executesql @sql, N''@bak nvarchar(260)'', @bak = @bak;

    SET @sql = N''ALTER DATABASE '' + QUOTENAME(@dst) + N'' SET MULTI_USER;'';
    EXEC sp_executesql @sql;
    SET @sql = N''ALTER DATABASE '' + QUOTENAME(@dst) + N'' SET RECOVERY SIMPLE;'';  -- disposable copy: no log growth
    EXEC sp_executesql @sql;

    EXEC master.sys.xp_delete_files @bak;

    FETCH NEXT FROM c INTO @src, @dst;
END
CLOSE c;
DEALLOCATE c;
';
GO
EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'nexora - staging refresh',
    @name = N'daily 01:00',
    @freq_type = 4,            -- daily
    @freq_interval = 1,
    @active_start_time = 010000;
GO
EXEC msdb.dbo.sp_add_jobserver @job_name = N'nexora - staging refresh';
GO
