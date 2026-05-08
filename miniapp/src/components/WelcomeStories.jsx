import { useEffect, useState } from 'react';
import { useT, useLang } from '../contexts/LangContext';
import { getStats, updateSettings, writeCache, readCache } from '../api/client';
import { track } from '../utils/analytics';

const STORAGE_KEY = 'wordsnap.welcome_seen';

const LANGS = [
  { code: 'uk', flag: '🇺🇦', name: 'Українська' },
  { code: 'en', flag: '🇬🇧', name: 'English' },
  { code: 'es', flag: '🇪🇸', name: 'Español' },
  { code: 'pl', flag: '🇵🇱', name: 'Polski' },
  { code: 'de', flag: '🇩🇪', name: 'Deutsch' },
];

const SLIDES = [
  {
    type: 'hero',
    photo: '/onboarding/slide_1.png',
    chips: [
      { text: 'Paragon', variant: 'light' },
      { textKey: 'welcome.snap.chip', variant: 'violet' },
    ],
    titleKey: 'welcome.snap.title',
    bodyKey: 'welcome.snap.body',
  },
  {
    type: 'srs',
    titleKey: 'welcome.srs.title',
    bodyKey: 'welcome.srs.body',
  },
  {
    type: 'lang-picker',
    field: 'native_lang',
    titleKey: 'welcome.native.title',
    bodyKey: 'welcome.native.body',
  },
  {
    type: 'lang-picker',
    field: 'target_lang',
    titleKey: 'welcome.target.title',
    bodyKey: 'welcome.target.body',
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

function SrsTimeline({ t }) {
  // Візуалізація інтервалів повторень. Збільшення відстані передає
  // центральну ідею: повторення розтягуються — слово закріплюється надовго.
  const stops = [
    { label: t('welcome.srs.now'), gap: 0 },
    { label: '2d', gap: 1 },
    { label: '4d', gap: 1.6 },
    { label: '8d', gap: 2.5 },
    { label: '21d', gap: 3.6, mastered: true },
  ];
  return (
    <div className="welcome-srs">
      {stops.map((s, i) => (
        <div key={i} className="welcome-srs-cell" style={{ flex: s.gap || 0.5 }}>
          {i > 0 && <div className="welcome-srs-line" />}
          <div className={`welcome-srs-bubble ${s.mastered ? 'mastered' : ''}`}>
            {s.mastered ? '✓' : s.label}
          </div>
        </div>
      ))}
    </div>
  );
}

function WelcomeStories({ onClose }) {
  const { t } = useT();
  const { setLang } = useLang();
  const [index, setIndex] = useState(0);
  const [selections, setSelections] = useState(() => {
    // Префіл з кешу stats — користувач який пройшов /start у боті побачить
    // обрану мову одразу і просто пройде далі.
    const cached = readCache('stats', { ignoreTtl: true }) || {};
    return {
      native_lang: cached.native_lang || null,
      target_lang: cached.target_lang || null,
    };
  });
  const [saving, setSaving] = useState(false);

  const slide = SLIDES[index];
  const isLast = index === SLIDES.length - 1;
  const isFirst = index === 0;

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    SLIDES.forEach(s => { if (s.photo) { const i = new Image(); i.src = s.photo; } });
    track('welcome_started', { total_steps: SLIDES.length });
    // Підкачуємо свіжі stats — якщо юзер уже мав налаштування, picker вже preselected
    getStats().then(r => {
      const data = r.data || {};
      writeCache('stats', data);
      setSelections(prev => ({
        native_lang: prev.native_lang || data.native_lang || null,
        target_lang: prev.target_lang || data.target_lang || null,
      }));
    }).catch(() => {});
    return () => { document.body.style.overflow = ''; };
  }, []);

  useEffect(() => {
    track('welcome_step_viewed', { n: index + 1, total: SLIDES.length, type: slide.type });
  }, [index, slide.type]);

  const persistAndClose = async (via) => {
    try {
      const patch = {};
      if (selections.native_lang) patch.native_lang = selections.native_lang;
      if (selections.target_lang) patch.target_lang = selections.target_lang;
      if (Object.keys(patch).length > 0) {
        setSaving(true);
        await updateSettings(patch);
        // Live-оновлення UI-мови, кешу stats — не треба зайвого fetch'у
        if (patch.native_lang) setLang(patch.native_lang);
        const cached = readCache('stats', { ignoreTtl: true }) || {};
        writeCache('stats', { ...cached, ...patch });
        track('lang_selected', { lang: patch.native_lang, role: 'native', source: 'miniapp_welcome' });
        if (patch.target_lang) {
          track('lang_selected', { lang: patch.target_lang, role: 'target', source: 'miniapp_welcome' });
        }
      }
    } catch { /* noop — наступне відкриття знов покаже welcome бо лангу не збережено */ }
    finally { setSaving(false); }

    try { localStorage.setItem(STORAGE_KEY, '1'); } catch {}
    if (via === 'complete') track('welcome_completed', { total_steps: SLIDES.length });
    else track('welcome_skipped', { at_step: index + 1, total_steps: SLIDES.length });
    onClose?.();
  };

  const next = () => {
    if (isLast) {
      persistAndClose('complete');
    } else {
      setIndex(i => i + 1);
    }
  };

  const back = () => {
    if (!isFirst) setIndex(i => i - 1);
  };

  const pickLang = (field, code) => {
    setSelections(prev => ({ ...prev, [field]: code }));
    // Невелика затримка щоб юзер встиг відчути feedback від тапу
    setTimeout(() => {
      if (field === SLIDES[index].field) {
        if (isLast) persistAndClose('complete');
        else setIndex(i => i + 1);
      }
    }, 280);
  };

  // CTA доступне тільки якщо зібрано всі обовʼязкові поля до цього кроку
  const canAdvance = (() => {
    if (slide.type !== 'lang-picker') return true;
    return !!selections[slide.field];
  })();

  return (
    <div className="welcome-overlay">
      <div className="welcome-top">
        <div className="welcome-brand">
          {!isFirst && (
            <button className="welcome-back" onClick={back} aria-label="Back" type="button">←</button>
          )}
          <span className="welcome-brand-text">WordSnap</span>
        </div>
        {/* "Skip" доступний тільки на perевих 2 explainer-слайдах. На lang-pickerах
            юзер мусить вибрати — це частина онбордингу, не косметика. */}
        {slide.type !== 'lang-picker' && (
          <button className="welcome-skip" onClick={() => persistAndClose('skip')}>
            {t('welcome.skip')}
          </button>
        )}
      </div>

      {/* Hero / SRS / Lang-picker visuals */}
      {slide.type === 'hero' && (
        <div className="welcome-hero">
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
        </div>
      )}

      {slide.type === 'srs' && (
        <div className="welcome-hero welcome-hero-srs">
          <SrsTimeline t={t} />
        </div>
      )}

      {slide.type === 'lang-picker' && (
        <div className="welcome-hero welcome-hero-picker">
          <div className="welcome-lang-grid">
            {LANGS.map(l => (
              <button
                key={l.code}
                className={`welcome-lang-btn ${selections[slide.field] === l.code ? 'active' : ''}`}
                onClick={() => pickLang(slide.field, l.code)}
                type="button"
                disabled={saving}
              >
                <span className="welcome-lang-flag">{l.flag}</span>
                <span className="welcome-lang-name">{l.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="welcome-content">
        <h1 className="welcome-display">{t(slide.titleKey)}</h1>
        <p className="welcome-sub">{t(slide.bodyKey)}</p>
      </div>

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
        {/* На lang-picker слайдах CTA-кнопка прихована: тап по мові сам
            переводить на наступний крок — менше тертя. */}
        {slide.type !== 'lang-picker' && (
          <button className="welcome-cta" onClick={next} disabled={!canAdvance || saving}>
            <span>{isLast ? t('welcome.start') : t('welcome.next')}</span>
            <span className="welcome-cta-arrow">→</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default WelcomeStories;
