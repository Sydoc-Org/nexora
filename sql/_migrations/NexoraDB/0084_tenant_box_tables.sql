IF OBJECT_ID('dbo.Tenants', 'U') IS NULL
CREATE TABLE dbo.Tenants (
    TenantCode        NVARCHAR(50)  NOT NULL,
    DisplayName       NVARCHAR(100) NOT NULL,
    OrganizationCode  NVARCHAR(5)   NOT NULL,  -- dbo.Organizations.organizationcode
    ClientCode        NVARCHAR(50)  NOT NULL,  -- dbo.Clients.ClientCode (data connection)
    IsActive          BIT NOT NULL CONSTRAINT DF_Tenants_IsActive DEFAULT (1),
    CONSTRAINT PK_Tenants PRIMARY KEY CLUSTERED (TenantCode),
    CONSTRAINT FK_Tenants_Organizations FOREIGN KEY (OrganizationCode)
        REFERENCES dbo.Organizations (organizationcode),
    CONSTRAINT FK_Tenants_Clients FOREIGN KEY (ClientCode)
        REFERENCES dbo.Clients (ClientCode)
);
GO
IF OBJECT_ID('dbo.TenantEntities', 'U') IS NULL
CREATE TABLE dbo.TenantEntities (
    TenantCode    NVARCHAR(50)  NOT NULL,
    EntityKey     NVARCHAR(100) NOT NULL,
    SourceObject  NVARCHAR(256) NOT NULL,  -- schema-qualified table/view, identifier-validated
    Kind          NVARCHAR(16)  NOT NULL,  -- documents | entries | lookup
    EngineRole    NVARCHAR(16)  NOT NULL CONSTRAINT DF_TenantEntities_EngineRole DEFAULT ('runtime'),
    IdColumn      NVARCHAR(128) NOT NULL,
    LabelEn       NVARCHAR(120) NOT NULL,
    LabelDe       NVARCHAR(120) NULL,
    LabelFr       NVARCHAR(120) NULL,
    LabelIt       NVARCHAR(120) NULL,
    SortOrder     INT NOT NULL CONSTRAINT DF_TenantEntities_SortOrder DEFAULT (100),
    Status        NVARCHAR(8)  NOT NULL CONSTRAINT DF_TenantEntities_Status DEFAULT ('draft'),
    CONSTRAINT PK_TenantEntities PRIMARY KEY CLUSTERED (TenantCode, EntityKey),
    CONSTRAINT FK_TenantEntities_Tenants FOREIGN KEY (TenantCode) REFERENCES dbo.Tenants (TenantCode),
    CONSTRAINT CK_TenantEntities_Kind CHECK (Kind IN ('documents','entries','lookup')),
    CONSTRAINT CK_TenantEntities_EngineRole CHECK (EngineRole IN ('runtime','stats','docfields')),
    CONSTRAINT CK_TenantEntities_Status CHECK (Status IN ('draft','active'))
);
GO
IF OBJECT_ID('dbo.TenantFields', 'U') IS NULL
CREATE TABLE dbo.TenantFields (
    TenantCode    NVARCHAR(50)  NOT NULL,
    EntityKey     NVARCHAR(100) NOT NULL,
    ColumnName    NVARCHAR(128) NOT NULL,  -- identifier-validated
    SemanticRole  NVARCHAR(16)  NOT NULL,  -- date|money|category|person|identifier|count|text|flag
    LookupEntity  NVARCHAR(100) NULL,      -- EntityKey of a Kind='lookup' entity
    LabelEn       NVARCHAR(120) NOT NULL,
    LabelDe       NVARCHAR(120) NULL,
    LabelFr       NVARCHAR(120) NULL,
    LabelIt       NVARCHAR(120) NULL,
    IsVisible     BIT NOT NULL CONSTRAINT DF_TenantFields_IsVisible DEFAULT (1),
    SortOrder     INT NOT NULL CONSTRAINT DF_TenantFields_SortOrder DEFAULT (100),
    Status        NVARCHAR(8)  NOT NULL CONSTRAINT DF_TenantFields_Status DEFAULT ('draft'),
    CONSTRAINT PK_TenantFields PRIMARY KEY CLUSTERED (TenantCode, EntityKey, ColumnName),
    CONSTRAINT FK_TenantFields_TenantEntities FOREIGN KEY (TenantCode, EntityKey)
        REFERENCES dbo.TenantEntities (TenantCode, EntityKey),
    CONSTRAINT CK_TenantFields_SemanticRole CHECK (SemanticRole IN
        ('date','money','category','person','identifier','count','text','flag')),
    CONSTRAINT CK_TenantFields_Status CHECK (Status IN ('draft','active'))
);
GO
IF OBJECT_ID('dbo.TenantPages', 'U') IS NULL
CREATE TABLE dbo.TenantPages (
    TenantCode  NVARCHAR(50)  NOT NULL,
    PageKey     NVARCHAR(100) NOT NULL,
    PageType    NVARCHAR(16)  NOT NULL,  -- list | crud | custom  (dashboard/report arrive later)
    EntityKey   NVARCHAR(100) NULL,      -- required for list/crud, NULL for custom
    LayoutJSON  NVARCHAR(MAX) NULL,      -- custom: {"endpoint": "...", "icon": "..."}
    SortOrder   INT NOT NULL CONSTRAINT DF_TenantPages_SortOrder DEFAULT (100),
    Status      NVARCHAR(8)  NOT NULL CONSTRAINT DF_TenantPages_Status DEFAULT ('draft'),
    CONSTRAINT PK_TenantPages PRIMARY KEY CLUSTERED (TenantCode, PageKey),
    CONSTRAINT FK_TenantPages_Tenants FOREIGN KEY (TenantCode) REFERENCES dbo.Tenants (TenantCode),
    CONSTRAINT CK_TenantPages_PageType CHECK (PageType IN ('list','crud','custom')),
    CONSTRAINT CK_TenantPages_Status CHECK (Status IN ('draft','active'))
);
GO
