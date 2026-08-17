USE [nexora]
GO
DROP USER [NT Service\SqlServerExtension]
GO
CREATE USER [NT Service\SqlServerExtension] FOR LOGIN [NT Service\SqlServerExtension] WITH DEFAULT_SCHEMA=[dbo]
GO
