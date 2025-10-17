import json

with open('data.json') as f:
    d = json.load(f)

for field in d['IndexFields']:
    if field['Name'] == 'CrdName':
        print('CrdName',field["FieldValue"]['Text'])
    elif field['Name'] == 'DocNo':
        print('DocNo',field["FieldValue"]['Text'])
    if field['Name'] == 'CrdNo':
        print('CrdNo',field["FieldValue"]['Text'])
    elif field['Name'] == 'GrossAmount':
        print('GrossAmount', field["FieldValue"]['Text'])
    elif field['Name'] == 'NetAmount':
        print( 'NetAmount',field["FieldValue"]['Text'])
    elif field['Name'] == 'VatAmount':
        print('VatAmount',field["FieldValue"]['Text'])
    elif field['Name'] == 'ImportDatetime':
        print('ImportDatetime',field["FieldValue"]['Text'])
    elif field['Name'] == 'ExportDatetime':
        print('ExportDatetime',field["FieldValue"]['Text'])
    elif field['Name'] == 'DocType':
        print('DocType',field["FieldValue"]['Text'])