Match the shape of what is loading — a 32px-tall bar for a KPI value, 13px bars for table cells.

```jsx
<Skeleton width={64} height={30} />
```

Requires the `nx-skel-shimmer` keyframes; they ship in `tokens/motion.css`… if you use Skeleton standalone, add the keyframes to your page.
