Frameless table. Put it straight inside a SectionRule — do not wrap it in `.nx-table-wrap`.

```jsx
<DataTable
  columns={[{ key: 'id', header: 'ID', mono: true }, { key: 'client', header: 'Kunde' },
            { key: 'count', header: 'Dokumente', align: 'right', mono: true }]}
  rows={rows} onRowClick={open} />
```
