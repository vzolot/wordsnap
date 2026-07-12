/**
 * Кільце прогресу вивчення слів (white-label статистика). Single-hue magnitude:
 * заповнена дуга (брендовий колір) на нейтральному треку показує частку
 * вивчених слів від усіх. Свідомо НЕ двоколірний донат «вивчено/вивчаю» —
 * у білому лейблі --violet може бути червоним (бренд), а mastered-зелений
 * поряд дав би red/green-плутанину для дальтоніків. Один тон + текстові
 * підписи — ідентичність не тільки кольором.
 */
export default function WordsProgress({ total, learned, labels }) {
  const t = Math.max(0, total | 0);
  const done = Math.min(t, Math.max(0, learned | 0));
  const learning = Math.max(0, t - done);
  const pct = t > 0 ? Math.round((done / t) * 100) : 0;

  const R = 52;
  const C = 2 * Math.PI * R;
  const dash = (pct / 100) * C;

  if (t === 0) {
    return (
      <div className="stat-cell" style={{ padding: 24, textAlign: 'center', color: 'var(--text-2)' }}>
        {labels.empty}
      </div>
    );
  }

  const Row = ({ color, label, value, muted }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{
        width: 10, height: 10, borderRadius: 3, flexShrink: 0,
        background: color || 'transparent',
        border: color ? 'none' : '1px solid var(--border)',
      }} />
      <span style={{ fontSize: 13, color: muted ? 'var(--text-2)' : 'var(--text-1)', flex: 1 }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{value}</span>
    </div>
  );

  return (
    <div className="stat-cell" style={{ padding: 18, display: 'flex', alignItems: 'center', gap: 18 }}>
      <svg width="118" height="118" viewBox="0 0 120 120" style={{ flexShrink: 0 }} role="img"
           aria-label={`${labels.mastered}: ${done} / ${t} (${pct}%)`}>
        <circle cx="60" cy="60" r={R} fill="none" stroke="var(--bg-card-2)" strokeWidth="12" />
        <circle cx="60" cy="60" r={R} fill="none" stroke="var(--violet)" strokeWidth="12"
                strokeLinecap="round" strokeDasharray={`${dash} ${C - dash}`}
                transform="rotate(-90 60 60)" />
        <text x="60" y="57" textAnchor="middle" fontSize="27" fontWeight="800"
              fill="var(--text-1)" style={{ letterSpacing: '-0.5px' }}>{pct}%</text>
        <text x="60" y="77" textAnchor="middle" fontSize="11" fill="var(--text-2)">{labels.mastered}</text>
      </svg>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 11, flex: 1, minWidth: 0 }}>
        <Row color="var(--violet)" label={labels.mastered} value={done} />
        <Row color="var(--bg-card-2)" label={labels.learning} value={learning} />
        <Row label={labels.total} value={t} muted />
      </div>
    </div>
  );
}
