import { isSpeechSupported, speak } from '../utils/speak';

function SpeakButton({ text, lang, size = 'md', className = '' }) {
  // Перевіряємо підтримку на РЕНДЕРІ (не раз при імпорті модуля) – інакше якщо
  // speechSynthesis ще не готовий на момент завантаження бандла, кнопка
  // зникала б назавжди.
  if (!text || !isSpeechSupported()) return null;

  const handle = (e) => {
    e.stopPropagation();
    e.preventDefault();
    speak(text, lang);
  };

  return (
    <button
      type="button"
      className={`speak-btn speak-btn-${size} ${className}`.trim()}
      onClick={handle}
      aria-label="Listen"
      title="Listen"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
      </svg>
    </button>
  );
}

export default SpeakButton;
