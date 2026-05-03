import { useEffect, useState } from 'react';
import { useT } from '../contexts/LangContext';

const STORAGE_KEY = 'wordsnap.welcome_seen';

const SLIDE_KEYS = [
  { title: 'welcome.slide1.title', body: 'welcome.slide1.body', accent: 'gradient' },
  { title: 'welcome.slide2.title', body: 'welcome.slide2.body', accent: 'violet' },
  { title: 'welcome.slide3.title', body: 'welcome.slide3.body', accent: 'pink' },
  { title: 'welcome.slide4.title', body: 'welcome.slide4.body', accent: 'gradient' },
  { title: 'welcome.slide5.title', body: 'welcome.slide5.body', accent: 'gradient' },
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
  const slide = SLIDE_KEYS[index];
  const isLast = index === SLIDE_KEYS.length - 1;

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  const finish = () => {
    try { localStorage.setItem(STORAGE_KEY, '1'); } catch {}
    onClose?.();
  };

  // Allow tap-to-advance: tap right side → next, left side → back
  const handleTap = (e) => {
    if (e.target.closest('.welcome-actions')) return;
    if (e.target.closest('.welcome-skip')) return;
    const w = e.currentTarget.offsetWidth;
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
    if (x < w / 3 && index > 0) setIndex(i => i - 1);
    else if (x > w / 3) {
      if (isLast) finish();
      else setIndex(i => i + 1);
    }
  };

  return (
    <div className={`welcome-overlay welcome-${slide.accent}`} onClick={handleTap}>
      <div className="welcome-progress">
        {SLIDE_KEYS.map((_, i) => (
          <div key={i} className={`welcome-bar ${i < index ? 'done' : ''} ${i === index ? 'active' : ''}`} />
        ))}
      </div>

      <button className="welcome-skip" onClick={finish}>{t('welcome.skip')}</button>

      <div className="welcome-content">
        <h1 className="welcome-title">{t(slide.title)}</h1>
        <p className="welcome-body">{t(slide.body)}</p>
      </div>

      <div className="welcome-actions">
        {isLast ? (
          <button className="btn btn-gradient welcome-cta" onClick={finish}>
            {t('welcome.start')}
          </button>
        ) : (
          <button className="btn btn-primary welcome-cta" onClick={() => setIndex(i => i + 1)}>
            {t('welcome.next')}
          </button>
        )}
      </div>
    </div>
  );
}

export default WelcomeStories;
