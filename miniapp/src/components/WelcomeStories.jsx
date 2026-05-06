import { useEffect, useState } from 'react';

const STORAGE_KEY = 'wordsnap.welcome_seen';

// PNG-слайди з усім контентом і текстом (англомовні).
// Згенеровані у Claude Design — копія у public/onboarding/.
const SLIDES = [
  '/onboarding/slide_1.png',
  '/onboarding/slide_2.png',
  '/onboarding/slide_3.png',
];

export function shouldShowWelcome() {
  // Тимчасово вимкнено — чекаємо на оновлений дизайн (з локалізацією).
  return false;
}

export function replayWelcome() {
  try { localStorage.removeItem(STORAGE_KEY); } catch {}
  window.dispatchEvent(new CustomEvent('wordsnap:replay-welcome'));
}

function WelcomeStories({ onClose }) {
  const [index, setIndex] = useState(0);
  const isLast = index === SLIDES.length - 1;

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    // Прелоадимо наступні слайди — щоб переходи були миттєві без миготіння
    SLIDES.forEach(src => { const i = new Image(); i.src = src; });
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
    <div className="welcome-overlay-png">
      {SLIDES.map((src, i) => (
        <img
          key={i}
          src={src}
          alt=""
          className={`welcome-slide-img ${i === index ? 'active' : ''}`}
          aria-hidden={i !== index}
          draggable={false}
        />
      ))}

      {/* Невидима кнопка Skip — поверх "Skip" що намальована у PNG (top-right) */}
      <button
        className="welcome-tap welcome-tap-skip"
        onClick={finish}
        aria-label="Skip"
      />

      {/* Невидима кнопка Get started — поверх кнопки що намальована у PNG (bottom) */}
      <button
        className="welcome-tap welcome-tap-cta"
        onClick={next}
        aria-label={isLast ? 'Get started' : 'Next'}
      />
    </div>
  );
}

export default WelcomeStories;
