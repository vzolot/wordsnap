// Легковажні SVG-графіки без бібліотек.
// timeline: масив { date, reviews, xp, added } від найстарішого до сьогодні.

const LINE_W = 320;
const LINE_H = 90;
const PAD_X = 6;
const PAD_TOP = 10;
const PAD_BOTTOM = 8;

export function XpLineChart({ timeline, label }) {
  if (!timeline?.length) return null;
  const xps = timeline.map(d => d.xp || 0);
  const maxXp = Math.max(1, ...xps);
  const innerW = LINE_W - PAD_X * 2;
  const innerH = LINE_H - PAD_TOP - PAD_BOTTOM;
  const stepX = innerW / Math.max(1, timeline.length - 1);

  const points = xps.map((v, i) => {
    const x = PAD_X + i * stepX;
    const y = PAD_TOP + innerH - (v / maxXp) * innerH;
    return [x, y];
  });

  const linePath = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L${(PAD_X + innerW).toFixed(1)},${LINE_H - PAD_BOTTOM} L${PAD_X.toFixed(1)},${LINE_H - PAD_BOTTOM} Z`;

  const totalXp = xps.reduce((s, v) => s + v, 0);
  const todayXp = xps[xps.length - 1] || 0;

  return (
    <div className="chart-card">
      <div className="chart-head">
        <span className="chart-eyebrow">{label}</span>
        <span className="chart-num">+{totalXp} XP</span>
      </div>
      <svg viewBox={`0 0 ${LINE_W} ${LINE_H}`} className="chart-svg" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="xp-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--violet)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--violet)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#xp-area)" />
        <path d={linePath} fill="none" stroke="var(--violet)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {points.length > 0 && (
          <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r="3.5" fill="var(--violet)" />
        )}
      </svg>
      <div className="chart-foot">
        <span>{timeline.length} {timeline.length === 1 ? 'day' : 'days'}</span>
        <span>today +{todayXp}</span>
      </div>
    </div>
  );
}

function intensityClass(activity, max) {
  if (activity <= 0) return 'lvl-0';
  const r = activity / Math.max(1, max);
  if (r < 0.25) return 'lvl-1';
  if (r < 0.5) return 'lvl-2';
  if (r < 0.75) return 'lvl-3';
  return 'lvl-4';
}

export function ActivityHeatmap({ timeline, label }) {
  if (!timeline?.length) return null;
  // Активність = reviews + added (нові + повторені)
  const cells = timeline.map(d => ({
    date: d.date,
    activity: (d.reviews || 0) + (d.added || 0),
    reviews: d.reviews || 0,
    added: d.added || 0,
  }));
  const maxActivity = Math.max(1, ...cells.map(c => c.activity));
  const activeDays = cells.filter(c => c.activity > 0).length;

  return (
    <div className="chart-card">
      <div className="chart-head">
        <span className="chart-eyebrow">{label}</span>
        <span className="chart-num">{activeDays}/{cells.length}</span>
      </div>
      <div className="heatmap-grid">
        {cells.map(c => (
          <div
            key={c.date}
            className={`heatmap-cell ${intensityClass(c.activity, maxActivity)}`}
            title={`${c.date}: ${c.reviews}r · ${c.added}+`}
          />
        ))}
      </div>
      <div className="chart-foot">
        <span>30d ago</span>
        <span className="heatmap-legend">
          <span className="heatmap-cell lvl-0" />
          <span className="heatmap-cell lvl-1" />
          <span className="heatmap-cell lvl-2" />
          <span className="heatmap-cell lvl-3" />
          <span className="heatmap-cell lvl-4" />
        </span>
        <span>today</span>
      </div>
    </div>
  );
}
