Replaces the boxed `.nx-filter` bar. One per page, directly under the PageHead.

```jsx
<FilterRow label="Prozess" right={<SegmentedControl options={['14 T','30 T','90 T']} value="14 T" onChange={setRange} />}>
  <ScopePicker groups={clients} selected={picked} onChange={setPicked} />
</FilterRow>
```
