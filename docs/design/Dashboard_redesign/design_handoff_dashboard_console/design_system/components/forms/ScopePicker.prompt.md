The scope filter used across nexora. Always pair it with the uppercase "Prozess" label in a FilterRow.

```jsx
<ScopePicker groups={clients} selected={picked} onChange={setPicked} />
```

Groups render as bold client rows, items as indented process rows with counts. Summary collapses to "Alle Prozesse" / "3 Prozesse".
