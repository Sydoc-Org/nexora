SET NOCOUNT ON;

MERGE INTO [dbo].[FieldMetadata] AS target
USING (VALUES
    ('grossamount',   'numeric',     1, 1),
    ('netamount',     'numeric',     1, 1),
    ('vatamount',     'numeric',     1, 1),
    ('docdate',       'date',        0, 1),
    ('doctype',       'categorical', 0, 1),
    ('docbarcode',    'categorical', 0, 1),
    ('crdno',         'categorical', 0, 1),
    ('crdname',       'categorical', 0, 1),
    ('bankpk',        'categorical', 0, 1),
    ('doccurrency',   'categorical', 0, 1),
    ('invoicenr',     'categorical', 0, 1),
    ('istec',         'categorical', 0, 1),
    ('esrreference',  'categorical', 0, 1),
    ('ordernumber',   'categorical', 0, 1),
    ('client',        'categorical', 0, 1),
    ('docsource',     'categorical', 0, 1),
    ('ownernr',       'categorical', 0, 1),
    ('tenancynr',     'categorical', 0, 1),
    ('registered',    'categorical', 0, 1),
    ('branch',        'categorical', 0, 1),
    ('forwarding',    'categorical', 0, 1),
    ('department',    'categorical', 0, 1),
    ('postcode',      'categorical', 0, 1),
    ('recipient',     'categorical', 0, 1),
    ('confidentiality','categorical',0, 1),
    ('propertynr',    'categorical', 0, 1),
    ('separatorsheet','categorical', 0, 1),
    ('docid',         'categorical', 0, 1),
    ('archiveboxno',  'categorical', 0, 1),
    ('scanbatchnr',                   'categorical', 0, 1),
    ('pid',                           'categorical', 0, 1),
    ('personalfileid',                'categorical', 0, 1),
    ('employmentfileid',              'categorical', 0, 1),
    ('doctypeidtargetsystem',         'categorical', 0, 1),
    ('doctypeidsydoc',                'categorical', 0, 1),
    ('registeridtargetsystem',        'categorical', 0, 1),
    ('masterdataseparatorsheettype',  'categorical', 0, 1),
    ('materdatabirthday',             'date',        0, 1),  -- column name has 'mater' typo in SearchConfig
    ('masterdatafirstname',           'categorical', 0, 1),
    ('masterdatalastname',            'categorical', 0, 1),
    ('masterdataseparatorsheetid',    'categorical', 0, 1),
    ('targetsystemfilename',          'categorical', 0, 1),
    ('emailfromaddress',              'categorical', 0, 1),
    -- synthetic dimensions (always available regardless of SearchConfig contents):
    ('processname',   'categorical', 0, 1),
    ('status',        'categorical', 0, 1)
) AS src (FieldKey, DataType, Aggregable, Sortable)
ON (target.FieldKey = src.FieldKey)
WHEN MATCHED THEN UPDATE SET DataType = src.DataType, Aggregable = src.Aggregable, Sortable = src.Sortable
WHEN NOT MATCHED THEN INSERT (FieldKey, DataType, Aggregable, Sortable) VALUES (src.FieldKey, src.DataType, src.Aggregable, src.Sortable);
