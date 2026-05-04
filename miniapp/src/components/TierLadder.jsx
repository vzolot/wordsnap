import { useT } from '../contexts/LangContext';

// Вертикальна шкала тірів XP. Показує всі рівні і нагороди (знижки),
// підсвічує поточний і прогрес до наступного.
function TierLadder({ tiers, totalXp, label }) {
  const { t } = useT();
  if (!tiers?.length) return null;

  const xp = totalXp || 0;
  // Поточний тір = найвищий де xp >= threshold.
  let currentIdx = 0;
  for (let i = 0; i < tiers.length; i++) {
    if (xp >= tiers[i].xp) currentIdx = i;
  }

  return (
    <div className="tier-ladder">
      {label && <div className="tier-ladder-label">{label}</div>}
      <ul className="tier-list">
        {tiers.map((tier, i) => {
          const achieved = xp >= tier.xp;
          const isCurrent = i === currentIdx;
          const isLast = i === tiers.length - 1;
          let progressPct = null;
          if (isCurrent && !isLast) {
            const nextXp = tiers[i + 1].xp;
            const span = nextXp - tier.xp;
            const got = Math.max(0, xp - tier.xp);
            progressPct = Math.min(100, Math.round((got / span) * 100));
          }

          return (
            <li
              key={tier.key}
              className={`tier-item ${achieved ? 'achieved' : ''} ${isCurrent ? 'current' : ''}`}
            >
              <div className="tier-rail">
                <div className={`tier-dot ${achieved ? 'on' : ''} ${isCurrent ? 'glow' : ''}`}>
                  {achieved ? '✓' : ''}
                </div>
                {!isLast && <div className={`tier-line ${achieved && xp >= tiers[i + 1].xp ? 'on' : isCurrent ? 'partial' : ''}`} />}
              </div>
              <div className="tier-body">
                <div className="tier-row-1">
                  <span className="tier-name">{t(tier.key)}</span>
                  <span className="tier-xp">{tier.xp.toLocaleString()} XP</span>
                </div>
                {tier.reward_key ? (
                  <div className="tier-reward">🎁 {t(tier.reward_key)}</div>
                ) : (
                  <div className="tier-reward muted">·</div>
                )}
                {isCurrent && progressPct != null && (
                  <div className="tier-progress">
                    <div className="tier-progress-track">
                      <div className="tier-progress-fill" style={{ width: `${progressPct}%` }} />
                    </div>
                    <div className="tier-progress-text">
                      {xp.toLocaleString()} / {tiers[i + 1].xp.toLocaleString()}
                    </div>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default TierLadder;
