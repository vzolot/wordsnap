import { useEffect, useState } from 'react';
import { useT } from '../contexts/LangContext';

const STORAGE_KEY = 'wordsnap.welcome_seen';

export function shouldShowWelcome() {
  try {
    return !localStorage.getItem(STORAGE_KEY);
  } catch {
    return true;
  }
}

export function replayWelcome() {
  try { localStorage.removeItem(STORAGE_KEY); } catch {}
  window.dispatchEvent(new CustomEvent('wordsnap:replay-welcome'));
}

const SLIDES = [
  { titleKey: 'welcome.s1.title', bodyKey: 'welcome.s1.body', visual: 'snap' },
  { titleKey: 'welcome.s2.title', bodyKey: 'welcome.s2.body', visual: 'cards' },
  { titleKey: 'welcome.s3.title', bodyKey: 'welcome.s3.body', visual: 'streak' },
];

// Декоративні SVG-візуали в стилі Preply (стек "карток" зі зміщенням)
function SnapVisual() {
  return (
    <div className="welcome-visual welcome-visual-stack">
      <div className="welcome-card welcome-card-back welcome-card-snap-back" />
      <div className="welcome-card welcome-card-mid welcome-card-snap-back" />
      <div className="welcome-card welcome-card-front">
        <div className="welcome-card-img" style={{ background: 'linear-gradient(135deg, #FCE7F3, #DDD6FE)' }}>
          <span style={{ fontSize: 56 }}>📸</span>
        </div>
        <div className="welcome-card-meta">
          <span className="welcome-chip welcome-chip-light">paragon</span>
          <span className="welcome-chip welcome-chip-violet">🇺🇦 чек</span>
        </div>
      </div>
    </div>
  );
}

function CardsVisual() {
  return (
    <div className="welcome-visual welcome-visual-stack">
      <div className="welcome-card welcome-card-back" />
      <div className="welcome-card welcome-card-mid" />
      <div className="welcome-card welcome-card-front welcome-card-word">
        <div className="welcome-word-meta">noun · b1</div>
        <div className="welcome-word-text">Termin</div>
        <div className="welcome-word-tr">🇺🇦 запис на прийом</div>
        <div className="welcome-word-ex">"Ich habe einen Termin um 10."</div>
        <div className="welcome-card-meta">
          <span className="welcome-chip welcome-chip-light">+10 XP</span>
          <span className="welcome-chip welcome-chip-violet">🔊</span>
        </div>
      </div>
    </div>
  );
}

function StreakVisual() {
  const cells = Array.from({ length: 21 }, (_, i) => i < 14);
  return (
    <div className="welcome-visual welcome-visual-stack">
      <div className="welcome-card welcome-card-front welcome-card-streak">
        <div className="welcome-streak-head">
          <span className="welcome-streak-flame">🔥</span>
          <span>
            <div className="welcome-streak-num">14 days</div>
            <div className="welcome-streak-label">streak</div>
          </span>
          <span className="welcome-chip welcome-chip-violet" style={{ marginLeft: 'auto' }}>+30 XP</span>
        </div>
        <div className="welcome-streak-grid">
          {cells.map((on, i) => (
            <div key={i} className={`welcome-streak-dot ${on ? 'on' : ''}`} />
          ))}
        </div>
        <div className="welcome-streak-tier">
          <span>Word Master</span>
          <span className="welcome-streak-reward">−25% Pro</span>
        </div>
      </div>
    </div>
  );
}

const VISUALS = { snap: SnapVisual, cards: CardsVisual, streak: StreakVisual };

function WelcomeStories({ onClose }) {
  const { t } = useT();
  const [index, setIndex] = useState(0);
  const slide = SLIDES[index];
  const isLast = index === SLIDES.length - 1;
  const Visual = VISUALS[slide.visual];

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  const finish = () => {
    try { localStorage.setItem(STORAGE_KEY, '1'); } catch {}
    onClose?.();
  };

  const next = () => {
    if (isLast) finish();
    else setIndex(i => i + 1);
  };

  return (
    <div className="welcome-overlay">
      <div className="welcome-top">
        <div className="welcome-brand">
          <span className="welcome-brand-mark">📸</span>
          <span className="welcome-brand-text">WordSnap</span>
        </div>
        {!isLast && (
          <button className="welcome-skip" onClick={finish}>{t('welcome.skip')}</button>
        )}
      </div>

      <div className="welcome-content">
        <Visual />

        <h1 className="welcome-display">{t(slide.titleKey)}</h1>
        <p className="welcome-sub">{t(slide.bodyKey)}</p>
      </div>

      <div className="welcome-bottom">
        <div className="welcome-dots">
          {SLIDES.map((_, i) => (
            <span key={i} className={`welcome-dot ${i === index ? 'active' : ''}`} />
          ))}
        </div>

        <button className="welcome-cta" onClick={next}>
          <span>{isLast ? t('welcome.start') : t('welcome.next')}</span>
          <span className="welcome-cta-arrow">→</span>
        </button>

        {!isLast && (
          <button className="welcome-skip-bottom" onClick={finish}>
            {t('welcome.skip')}
          </button>
        )}
      </div>
    </div>
  );
}

export default WelcomeStories;
