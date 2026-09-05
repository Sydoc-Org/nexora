// Persistent icon rail + page container. Mirrors _header.html: 64px collapsed
// rail on white, expanding to 220px, active item marked by a 3px accent bar.
function Shell({ active, onNavigate, children }) {
  const [open, setOpen] = React.useState(false);
  const items = [
    { id: 'dashboard', icon: 'fas fa-gauge-high', label: 'Dashboard' },
    { id: 'workitems', icon: 'fas fa-list-check', label: 'Workitems' },
    { id: 'reporting', icon: 'fas fa-chart-line', label: 'Reporting' },
    { id: 'documents', icon: 'fas fa-file-lines', label: 'Dokumente' },
    { id: 'appearance', icon: 'fas fa-sliders', label: 'Darstellung' }
  ];
  const railW = open ? 220 : 64;
  return (
    <div style={{ minHeight: '100%', background: 'var(--nx-page)' }}>
      <nav
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        style={{
          position: 'fixed', left: 0, top: 0, height: '100%', width: railW, zIndex: 40,
          display: 'flex', flexDirection: 'column', background: 'var(--nx-card)',
          borderRight: '1px solid var(--nx-divider)', overflow: 'hidden',
          transition: 'width .28s var(--nx-ease)'
        }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, height: 64, padding: '0 12px', borderBottom: '1px solid var(--nx-divider)', flexShrink: 0 }}>
          <img src="../../assets/nexora-logo.gif" alt="nexora" style={{ width: 38, height: 38, flexShrink: 0 }} />
          <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.3px', color: 'var(--nx-text)', opacity: open ? 1 : 0, transition: 'opacity .18s', whiteSpace: 'nowrap' }}>nexora</span>
        </div>
        <div style={{ flex: 1, padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {items.map(it => {
            const on = it.id === active;
            return (
              <button key={it.id} onClick={() => onNavigate && onNavigate(it.id)}
                style={{
                  position: 'relative', display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 8px', borderRadius: 'var(--nx-radius-ctl)', border: 'none',
                  background: on ? 'rgba(0,0,0,.05)' : 'transparent', cursor: 'pointer',
                  color: on ? 'var(--nx-text)' : 'var(--nx-text-sec)',
                  fontFamily: 'var(--nx-font)', fontSize: 13, fontWeight: 500, textAlign: 'left', width: '100%'
                }}>
                {on ? <span style={{ position: 'absolute', left: -8, top: '50%', transform: 'translateY(-50%)', width: 3, height: 24, borderRadius: '0 2px 2px 0', background: 'var(--nx-brand-grad)' }} /> : null}
                <i className={it.icon} style={{ width: 16, textAlign: 'center', fontSize: 13 }} />
                <span style={{ opacity: open ? 1 : 0, transition: 'opacity .18s', whiteSpace: 'nowrap' }}>{it.label}</span>
              </button>
            );
          })}
        </div>
        <div style={{ padding: '12px 8px', borderTop: '1px solid var(--nx-divider)', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ width: 26, height: 26, borderRadius: 99, background: 'var(--nx-sunken)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--nx-text-sec)', flexShrink: 0 }}>BS</span>
          <span style={{ fontSize: 12, color: 'var(--nx-text-sec)', opacity: open ? 1 : 0, transition: 'opacity .18s', whiteSpace: 'nowrap' }}>Ben Streich</span>
        </div>
      </nav>
      <main style={{ paddingLeft: 64 }}>
        <div style={{ maxWidth: 'var(--content-max)', margin: '0 auto', padding: '32px 22px 40px', boxSizing: 'border-box' }}>
          {children}
        </div>
      </main>
    </div>
  );
}
window.NexoraKitShell = Shell;
