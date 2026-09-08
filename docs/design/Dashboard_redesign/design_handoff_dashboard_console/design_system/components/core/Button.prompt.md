Standard nexora action control — use for every button in a slim page, sized to match the filter row it sits in.

```jsx
<Button icon="fas fa-rotate">Aktualisieren</Button>
<Button variant="primary" size="lg">Bericht ausführen</Button>
```

Variants: `secondary` (default, white on hairline border), `primary` (solid accent — one per view), `tint` (accent-tint fill, for a secondary accent action), `ghost` (toolbars, kebab rows), `danger`. Sizes: `sm` 27px, `md` 29px (slim rows), `lg` 33px (console rows). The old gradient CTA (`.nx-btn--primary` in nexora-ui.css) is retired in the slim system — primary is a flat accent fill.
