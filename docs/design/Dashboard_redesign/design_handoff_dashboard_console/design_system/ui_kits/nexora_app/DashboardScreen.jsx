// The approved slim dashboard (option 1a of the redesign): page head, one
// filter line, borderless KPI strip, full-width tabbed chart, backlog trend.
function DashboardScreen({ NS }) {
  const { PageHead, Button, FilterRow, ScopePicker, SegmentedControl, ChartHeader, UnderlineTabs, KpiStrip, SectionRule, SeriesLegend } = NS;
  const { LineChart, BarChart } = window.NexoraKitCharts;
  const [range, setRange] = React.useState('14 T');
  const [view, setView] = React.useState('time');
  const [picked, setPicked] = React.useState(['02', '03', '01']);
  const [countdown, setCountdown] = React.useState(27);
  React.useEffect(() => {
    const t = setInterval(() => setCountdown(c => (c <= 1 ? 30 : c - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  const groups = [{ name: 'Generali', items: [
    { id: '02', name: '02_Posteingang', count: 612 },
    { id: '03', name: '03_Invoice_New', count: 341 },
    { id: '01', name: '01_Scan_Eingang', count: 188 },
    { id: '04', name: '04_Archiv', count: 106 }
  ] }];

  const days = ['08-18','08-19','08-20','08-21','08-22','08-23','08-24','08-25','08-26','08-27','08-28','08-29','08-30','09-01'];
  const daily = [1980, 2410, 2650, 1120, 640, 2380, 2510, 2290, 2620, 1080, 590, 2440, 2560, 1870];
  const hours = ['06','07','08','09','10','11','12','13','14','15','16','17','18','19'];
  const hourly = [12, 48, 130, 96, 84, 61, 34, 72, 88, 65, 40, 22, 9, 3];

  const backlog = [
    { name: '02_Posteingang', color: 'var(--nx-series-1)', dash: 'solid', count: 612, values: [402,556,448,624,512,668,470,602,706,520,638,724,536,612] },
    { name: '03_Invoice_New', color: 'var(--nx-series-2)', dash: 'dashed', count: 341, values: [206,302,244,372,262,348,232,396,288,246,402,296,234,341] },
    { name: '01_Scan_Eingang', color: 'var(--nx-series-3)', dash: 'dotted', count: 188, values: [176,118,214,132,196,108,226,148,122,232,158,114,218,188] },
    { name: '04_Archiv', color: 'var(--nx-series-4)', dash: 'solid', count: 106, values: [56,118,72,142,92,66,132,76,156,96,72,138,80,106] }
  ];

  return (
    <div>
      <PageHead icon="fas fa-gauge-high" title="Dashboard"
        meta="Ben Streich · letzte Anmeldung 31.08.2026 21:05"
        status={'Aktualisiert 06:47:12 · neu in ' + countdown + 's'}
        actions={<Button icon="fas fa-rotate">Aktualisieren</Button>} />

      <FilterRow label="Prozess"
        right={<SegmentedControl options={['14 T','30 T','90 T']} value={range} onChange={setRange} />}>
        <ScopePicker groups={groups} selected={picked} onChange={setPicked} />
      </FilterRow>

      <KpiStrip items={[
        { label: 'Heute importiert', value: '595', delta: '+12%', deltaTone: 'good', spark: [420,500,470,520,560,480,595], sparkColor: 'var(--nx-series-1)' },
        { label: 'Heute verarbeitet', value: '60', delta: '−38%', deltaTone: 'bad', spark: [180,220,140,190,160,97,60], sparkColor: 'var(--nx-series-5)' },
        { label: 'Aktueller Rückstand', value: '1,247', delta: '+4%', deltaTone: 'bad', spark: [980,1020,1110,1080,1150,1199,1247], sparkColor: 'var(--nx-series-1)' },
        { label: 'Ø Verarbeitungszeit', value: '15h', delta: '−1.5h', deltaTone: 'good', spark: [19,18.5,17,17.5,16.2,16.5,15], sparkColor: 'var(--nx-series-5)' }
      ]} />

      <div style={{ padding: '16px 0 8px', marginTop: 6 }}>
        <ChartHeader
          title={view === 'time' ? 'Verarbeitete Dokumente im Zeitverlauf' : 'Heute verarbeitete Dokumente nach Stunde'}
          meta={view === 'time' ? '14 Tage · Spitze 2,650' : 'Spitze 130 um 08:00'}
          right={<UnderlineTabs value={view} onChange={setView}
            tabs={[{ label: 'Zeitverlauf', value: 'time' }, { label: 'Heute nach Stunde', value: 'hour' }]} />} />
        <div style={{ marginTop: 14 }}>
          {view === 'time'
            ? <LineChart labels={days} roundTo={500} series={[{ name: 'Verarbeitet', color: 'var(--nx-series-1)', values: daily }]} />
            : <BarChart labels={hours} values={hourly} roundTo={35} />}
        </div>
      </div>

      <SectionRule title="Rückstand" meta="1,247 offen · +48 seit gestern"
        eyebrow="Verlauf 14 Tage"
        right={<SeriesLegend items={backlog.map(b => ({ name: b.name, color: b.color, dash: b.dash, count: b.count }))} />}>
        <LineChart labels={days} height={200} roundTo={400}
          series={backlog.map(b => ({ name: b.name, color: b.color, dash: b.dash, values: b.values }))} />
      </SectionRule>
    </div>
  );
}
window.NexoraKitDashboard = DashboardScreen;
