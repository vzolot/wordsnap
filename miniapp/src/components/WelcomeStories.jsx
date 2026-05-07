import { useEffect, useState } from 'react';
import { useT } from '../contexts/LangContext';
import { track } from '../utils/analytics';

const STORAGE_KEY = 'wordsnap.welcome_seen';

const SLIDES = [
  {
    photo: '/onboarding/slide_1.png',
    chips: [
      { text: 'Paragon', variant: 'light' },
      { textKey: 'welcome.s1.chip2', variant: 'violet' },
    ],
    titleKey: 'welcome.s1.title',
    bodyKey: 'welcome.s1.body',
  },
  {
    photo: null,
    titleKey: 'welcome.s2.title',
    bodyKey: 'welcome.s2.body',
  },
  {
    photo: null,
    titleKey: 'welcome.s3.title',
    bodyKey: 'welcome.s3.body',
  },
];

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

function WelcomeStories({ onClose }) {
  const { t } = useT();
  const [index, setIndex] = useState(0);
  const slide = SLIDES[index];
  const isLast = index === SLIDES.length - 1;
  const isFirst = index === 0;

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    SLIDES.forEach(s => { if (s.photo) { const i = new Image(); i.src = s.photo; } });
    track('welcome_started', { total_steps: SLIDES.length });
    return () => { document.body.style.overflow = ''; };
  }, []);

  useEffect(() => {
    track('welcome_step_viewed', { n: index + 1, total: SLIDES.length });
  }, [index]);

  const finish = (via) => {
    try { localStorage.setItem(STORAGE_KEY, '1'); } catch {}
    if (via === 'complete') track('welcome_completed', { total_steps: SLIDES.length });
    else track('welcome_skipped', { at_step: index + 1, total_steps: SLIDES.length });
    onClose?.();
  };

  const next = () => {
    if (isLast) finish('complete');
    else setIndex(i => i + 1);
  };

  const back = () => {
    if (!isFirst) setIndex(i => i - 1);
  };

  return (
    <div className="welcome-overlay">
      {/* Top bar */}
      <div className="welcome-top">
        <div className="welcome-brand">
          {!isFirst && (
            <button
              className="welcome-back"
              onClick={back}
              aria-label="Back"
              type="button"
            >
              ←
            </button>
          )}
          <span className="welcome-brand-text">WordSnap</span>
        </div>
        <button className="welcome-skip" onClick={() => finish('skip')}>
          {t('welcome.skip')}
        </button>
      </div>

      {/* Hero */}
      <div className="welcome-hero">
        {slide.photo ? (
          <>
            <img src={slide.photo} alt="" className="welcome-hero-photo" draggable={false} />
            {slide.chips && (
              <div className="welcome-hero-chips">
                {slide.chips.map((chip, i) => (
                  <span key={i} className={`welcome-chip welcome-chip-${chip.variant}`}>
                    {chip.textKey ? t(chip.textKey) : chip.text}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="welcome-hero-spacer" />
        )}
      </div>

      {/* Headline + body */}
      <div className="welcome-content">
        <h1 className="welcome-display">{t(slide.titleKey)}</h1>
        <p className="welcome-sub">{t(slide.bodyKey)}</p>
      </div>

      {/* Bottom — clickable dots + CTA */}
      <div className="welcome-bottom">
        <div className="welcome-dots">
          {SLIDES.map((_, i) => (
            <button
              key={i}
              className={`welcome-dot ${i === index ? 'active' : ''}`}
              onClick={() => setIndex(i)}
              aria-label={`Slide ${i + 1}`}
              type="button"
            />
          ))}
        </div>
        <button className="welcome-cta" onClick={next}>
          <span>{isLast ? t('welcome.start') : t('welcome.next')}</span>
          <span className="welcome-cta-arrow">→</span>
        </button>
      </div>
    </div>
  );
}

export default WelcomeStories;
