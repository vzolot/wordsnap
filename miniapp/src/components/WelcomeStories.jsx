import { useEffect, useState } from 'react';
import { useT, useLang } from '../contexts/LangContext';
import { useTenant } from '../contexts/TenantContext';
import { useRole } from '../contexts/RoleContext';
import { getStats, updateSettings, writeCache, readCache } from '../api/client';
import { track } from '../utils/analytics';

const STORAGE_KEY = 'wordsnap.welcome_seen';

const LANGS = [
  { code: 'uk', flag: '🇺🇦', name: 'Українська' },
  { code: 'en', flag: '🇬🇧', name: 'English' },
  { code: 'fr', flag: '🇫🇷', name: 'Français' },
  { code: 'es', flag: '🇪🇸', name: 'Español' },
  { code: 'pl', flag: '🇵🇱', name: 'Polski' },
  { code: 'de', flag: '🇩🇪', name: 'Deutsch' },
];

// Самостійний учень (базовий WordSnap): снап-фото, SRS і вибір мов.
const DEFAULT_SLIDES = [
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

// Учень white-label тенанта: слова дає викладач, вибирати мову не треба —
// пара сторінок про сам процес користування.
const WL_STUDENT_SLIDES = [
  {
    type: 'icon', emoji: '📚',
    title: 'Навчання з викладачем',
    body: 'Ваш викладач додає вам слова та колоди — вони одразу зʼявляться тут. Нічого налаштовувати не треба.',
  },
  {
    type: 'srs',
    title: 'Повторюйте у потрібний момент',
    body: 'Слова показуються за інтервальним повторенням — так вони закріплюються надовго.',
  },
  {
    type: 'icon', emoji: '📅',
    title: 'Записуйтесь на уроки',
    body: 'У розділі «Уроки» оберіть вільний час і забронюйте заняття з викладачем.',
  },
];

// Викладач: як додавати слова, вести календар і дивитись прогрес.
const TEACHER_SLIDES = [
  {
    type: 'icon', emoji: '📸',
    title: 'Додавайте слова учням',
    body: 'Створюйте колоди вручну або сфотографуйте сторінку підручника — застосунок сам розпізнає слова й переклади.',
  },
  {
    type: 'srs',
    title: 'Учні повторюють у потрібний момент',
    body: 'Слова показуються учням за інтервальним повторенням — вони закріплюють їх саме тоді, коли починають забувати.',
  },
  {
    type: 'icon', emoji: '📅',
    title: 'Календар і статистика',
    body: 'Відкрийте вільні години для запису на уроки та стежте за прогресом кожного учня у вкладці «Статистика».',
  },
];

// Власник школи: запросити команду, призначити учнів, керувати підпискою.
const OWNER_SLIDES = [
  {
    type: 'icon', emoji: '🏫',
    title: 'Запросіть команду',
    body: 'У вкладці «Школа» надішліть посилання-запрошення викладачам, потім учням — і призначте кожному учню викладача.',
  },
  {
    type: 'icon', emoji: '📅',
    title: 'Розклади викладачів',
    body: 'У «Календар» оберіть викладача й перегляньте або складіть його розклад — усе в одному місці.',
  },
  {
    type: 'icon', emoji: '📊',
    title: 'Статистика та оплата',
    body: 'Дивіться статистику викладачів, а внизу «Статистика» — керуйте підпискою: $19/міс за першого викладача, +$5 за кожного наступного.',
  },
];

function slidesFor({ isTeacher, role, is_school, isDefaultTenant }) {
  if (isTeacher) return (role === 'owner' && is_school) ? OWNER_SLIDES : TEACHER_SLIDES;
  if (!isDefaultTenant) return WL_STUDENT_SLIDES;
  return DEFAULT_SLIDES;
}

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

function SrsTimeline() {
  // Roadmap: 5 рівновіддалених точок зі з'єднувальною лінією під ними.
  // Інтервал — у самому кружечку. Останній — checkmark у бренд-градієнті.
  const stops = [
    { label: '1d' },
    { label: '2d' },
    { label: '4d' },
    { label: '8d' },
    { mastered: true },
  ];
  return (
    <div className="welcome-srs">
      {stops.map((s, i) => (
        <div key={i} className="welcome-srs-step">
          {i > 0 && <div className="welcome-srs-track" />}
          <div className={`welcome-srs-dot ${s.mastered ? 'mastered' : ''}`}>
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
  const { is_school, isDefaultTenant, display_name } = useTenant();
  const { role, isTeacher } = useRole();
  const SLIDES = slidesFor({ isTeacher, role, is_school, isDefaultTenant });
  const brandName = display_name || 'WordSnap';
  const [rawIndex, setIndex] = useState(0);
  // Роль/тенант можуть дозавантажитись після відкриття — набір слайдів
  // змінюється реактивно, тож затискаємо індекс у межах поточного набору.
  const index = Math.min(rawIndex, SLIDES.length - 1);
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
    // Тільки виставляємо вибір — без auto-advance. Юзер сам тапне "Далі"
    // коли готовий, або переключиться між мовами якщо передумав.
    setSelections(prev => ({ ...prev, [field]: code }));
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
          <span className="welcome-brand-text">{brandName}</span>
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
          <SrsTimeline />
        </div>
      )}

      {slide.type === 'icon' && (
        <div className="welcome-hero welcome-hero-icon">
          <div className="welcome-icon-badge">{slide.emoji}</div>
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
        <h1 className="welcome-display">{slide.titleKey ? t(slide.titleKey) : slide.title}</h1>
        <p className="welcome-sub">{slide.bodyKey ? t(slide.bodyKey) : slide.body}</p>
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
        <button className="welcome-cta" onClick={next} disabled={!canAdvance || saving}>
          <span>{isLast ? t('welcome.start') : t('welcome.next')}</span>
          <span className="welcome-cta-arrow">→</span>
        </button>
      </div>
    </div>
  );
}

export default WelcomeStories;
