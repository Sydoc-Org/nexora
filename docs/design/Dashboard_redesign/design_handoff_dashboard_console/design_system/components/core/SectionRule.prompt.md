Use instead of `<div className="nx-card">` for page content. Sections stack, each separated from the previous by its own top rule.

```jsx
<SectionRule title="Rückstand" meta="1,247 offen · +48 seit gestern"
  right={<SeriesLegend items={legend} />} eyebrow="Verlauf 14 Tage">
  <BacklogChart />
</SectionRule>
```

Never nest a SectionRule inside another one; sections are always siblings.
