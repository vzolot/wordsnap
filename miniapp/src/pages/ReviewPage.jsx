import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getReviewWords, getWeakReviewWords, getWords, readCache, submitReview, writeCache } from '../api/client';
import { useT } from '../contexts/LangContext';
import { track } from '../utils/analytics';
import { optimizeImage } from '../utils/optimizeImage';
import AppBar from '../components/AppBar';
import SpeakButton from '../components/SpeakButton';
import WordPlaceholder from '../components/WordPlaceholder';
import { ReviewSkeleton } from '../components/Skeleton';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱', de: '🇩🇪', fr: '🇫🇷' };

const MODES = ['cards', 'quiz', 'spelling'];

function normalize(s) {
  return (s || '').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function pickDistractors(pool, current, n) {
  const pickFrom = pool.filter(
    w => w && w.id !== current.id && w.translation && w.translation !== current.translation
  );
  // shuffle copy
  for (let i = pickFrom.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pickFrom[i], pickFrom[j]] = [pickFrom[j], pickFrom[i]];
  }
  // унікальні переклади (бо у користувача можуть бути дублі)
  const seen = new Set();
  const out = [];
  for (const w of pickFrom) {
    if (seen.has(w.translation)) continue;
    seen.add(w.translation);
    out.push(w);
    if (out.length >= n) break;
  }
  return out;
}

function ReviewPage() {
  const [words, setWords] = useState([]);
  const [pool, setPool] = useState([]);            // ширший пул для distractors
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [stats, setStats] = useState({ reviewed: 0, mastered: 0, xp: 0 });
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t, lang } = useT();

  const mode = MODES.includes(searchParams.get('mode')) ? searchParams.get('mode') : 'cards';
  const setMode = (m) => {
    if (m !== mode) track('review_mode_selected', { mode: m, from: mode });
    // Зберігаємо позицію в черзі (index), сесію (stats) та done-стан між
    // режимами. Раніше переключення скидало index=0 → ті самі слова
    // показувались наново → submitReview викликався вдруге → XP дублювався.
    setSearchParams({ mode: m });
  };

  // src=weak → тренування по слабких словах (з передурочного дайджесту, M10).
  const src = searchParams.get('src');
  useEffect(() => {
    const loader = src === 'weak' ? getWeakReviewWords : getReviewWords;
    loader().then(r => {
      setWords(r.data || []);
      setLoading(false);
    }).catch(() => setLoading(false));
    // distractor pool – кешований getWords щоб не блокувати
    const cached = readCache('words');
    if (cached) setPool(cached);
    getWords().then(r => setPool(r.data || [])).catch(() => {});
  }, []);

  const current = words[index];

  // Image-prefetch: the user flagged on 2026-06-09 that swapping to the next
  // word briefly shows the PREVIOUS image (~200-500 ms) before the new one
  // paints. Two causes: (a) React reconciles the same <img> element when
  // `current` changes, so the browser keeps showing the old src until the
  // new one loads – already mitigated by the `key={current.id}` on each
  // <img> (forces unmount/remount, instantly clears stale image). (b) The
  // new image still has to be downloaded fresh, which is the actual delay
  // visible to the user. Mitigate (b) by warming the browser cache: spin
  // up `new Image()` objects for the next 2 words in the queue as soon as
  // we advance. When the user taps Easy/Hard/Forgot, the next card's image
  // is already in cache and paints on the same frame.
  useEffect(() => {
    const next = [words[index + 1], words[index + 2]].filter(
      w => w && w.image_url
    );
    next.forEach(w => {
      const img = new Image();
      img.src = optimizeImage(w.image_url);
    });
  }, [index, words]);

  const advance = (quality) => {
    const xpGain = quality === 5 ? 10 : quality === 3 ? 6 : 2;
    setStats(s => ({
      reviewed: s.reviewed + 1,
      mastered: s.mastered + (quality === 5 ? 1 : 0),
      xp: s.xp + xpGain,
    }));
    submitReview(current.id, quality, mode).catch(() => {});

    // Оптимістично оновлюємо кеш stats – щоб HomePage при поверненні
    // ВІДРАЗУ показав актуальні цифри без блимання нулями.
    const cachedStats = readCache('stats', { ignoreTtl: true });
    if (cachedStats) {
      writeCache('stats', {
        ...cachedStats,
        total_reviews: (cachedStats.total_reviews || 0) + 1,
        reviewed_today: (cachedStats.reviewed_today || 0) + 1,
        xp_today: (cachedStats.xp_today || 0) + xpGain,
        total_xp: (cachedStats.total_xp || 0) + xpGain,
      });
    }

    // Прибираємо щойно повторене слово з кешу review-черги (а не дропаємо
    // весь кеш). Так due-count на Home декрементиться миттєво.
    const cachedReview = readCache('review', { ignoreTtl: true });
    if (Array.isArray(cachedReview)) {
      writeCache('review', cachedReview.filter(w => w.id !== current.id));
    }

    setTimeout(() => {
      if (index + 1 >= words.length) setDone(true);
      else setIndex(i => i + 1);
    }, 200);
  };

  if (loading) {
    return <><AppBar /><ReviewSkeleton /></>;
  }

  if (words.length === 0) {
    return (
      <>
        <AppBar />
        <div className="page">
          <div className="empty-state">
            <div className="empty-illu">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="1.5">
                <path d="M4 4h12l4 4v12H4z" />
                <line x1="8" y1="11" x2="16" y2="11" />
                <line x1="8" y1="15" x2="14" y2="15" />
              </svg>
            </div>
            <h2 className="empty-title">{t('review.empty.title')}</h2>
            <p className="empty-sub">{t('review.empty.sub')}</p>
            <button className="btn btn-gradient" onClick={() => navigate('/')}>{t('review.empty.cta')}</button>
          </div>
        </div>
      </>
    );
  }

  if (done) {
    const masteredPart = stats.mastered > 0 ? t('review.complete.mastered_part', { n: stats.mastered }) : '';
    return (
      <>
        <AppBar />
        <div className="page" style={{ textAlign: 'center', paddingTop: 30 }}>
          <div className="success-circle">
            <svg className="success-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12l5 5L20 7" />
            </svg>
          </div>
          <h1 className="h-display" style={{ marginBottom: 8 }}>{t('review.complete.title')}</h1>
          <p className="body-2" style={{ marginBottom: 22, padding: '0 16px' }}>
            {t('review.complete.summary', { reviewed: stats.reviewed, mastered: masteredPart })}
          </p>

          <div className="stats-row" style={{ marginBottom: 22 }}>
            <div className="stat-cell">
              <div className="stat-num">{stats.reviewed}</div>
              <div className="stat-label">{t('review.complete.reviewed')}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-num violet">+{stats.xp} XP</div>
              <div className="stat-label">{t('review.complete.earned')}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-num">{stats.mastered}</div>
              <div className="stat-label">{t('review.complete.mastered')}</div>
            </div>
          </div>

          <button className="btn btn-primary" onClick={() => navigate('/')}>{t('review.back_home')}</button>
        </div>
      </>
    );
  }

  return (
    <>
      <AppBar />

      <div className="page">
        <div className="review-mode-chips">
          <button
            className={`review-mode-chip ${mode === 'cards' ? 'active' : ''}`}
            onClick={() => setMode('cards')}
            type="button"
          >{t('review.mode.cards')}</button>
          <button
            className={`review-mode-chip ${mode === 'quiz' ? 'active' : ''}`}
            onClick={() => setMode('quiz')}
            type="button"
          >{t('review.mode.quiz')}</button>
          <button
            className={`review-mode-chip ${mode === 'spelling' ? 'active' : ''}`}
            onClick={() => setMode('spelling')}
            type="button"
          >{t('review.mode.spelling')}</button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <span className="body-2" style={{ fontWeight: 700, color: 'var(--text-1)' }}>
            {index + 1} / {words.length}
          </span>
          <div className="progress-track" style={{ flex: 1 }}>
            <div className="progress-fill" style={{ width: `${(index / words.length) * 100}%` }} />
          </div>
        </div>

        {current && mode === 'cards' && <CardsMode key={current.id} current={current} onAnswer={advance} t={t} lang={lang} />}
        {current && mode === 'quiz' && <QuizMode key={current.id} current={current} pool={pool.length ? pool : words} onAnswer={advance} t={t} lang={lang} />}
        {current && mode === 'spelling' && <SpellingMode key={current.id} current={current} onAnswer={advance} t={t} lang={lang} />}
      </div>
    </>
  );
}

function CardsMode({ current, onAnswer, t, lang }) {
  const [revealed, setRevealed] = useState(false);
  const [selected, setSelected] = useState(null);

  useEffect(() => { setRevealed(false); setSelected(null); }, [current.id]);

  // До 3 прикладів із поясненням – як у картці основного WordSnap.
  const examples = Array.isArray(current.examples) ? current.examples.slice(0, 3) : [];

  const handle = (q, k) => {
    if (selected) return;
    setSelected(k);
    onAnswer(q);
  };

  return (
    <>
      <div className="review-card">
        {current.image_url
          ? <img key={current.id} src={optimizeImage(current.image_url)} alt="" className="review-image" />
          : <WordPlaceholder word={current.word} className="review-image" />}
        <div className="review-pos">{current.part_of_speech || ''}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center' }}>
          <div className="review-word">{current.word}</div>
          <SpeakButton text={current.word} lang={current.target_lang} size="md" />
        </div>

        {!revealed ? (
          <button className="btn-pill" style={{ marginTop: 18 }} onClick={() => setRevealed(true)}>
            {t('review.reveal')}
          </button>
        ) : (
          <>
            <div className="review-translation-box">
              <div className="translation-eyebrow">{t('review.translation')}</div>
              <div className="translation-text">{FLAGS[lang] || ''} {current.translation}</div>
              {current.memory_tip && <div className="translation-sub">{current.memory_tip}</div>}
            </div>
            {examples.length > 0 && (
              <div className="review-examples">
                <div className="eyebrow" style={{ padding: '0 4px' }}>{t('review.example')}</div>
                {examples.map((ex, i) => {
                  const sentence = typeof ex === 'string' ? ex : ex?.sentence;
                  const explanation = typeof ex === 'string' ? null : ex?.explanation;
                  if (!sentence) return null;
                  return (
                    <div key={i} className="review-example">
                      <div>&quot;{sentence}&quot;</div>
                      {explanation && <div className="translation-sub" style={{ marginTop: 2 }}>{explanation}</div>}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {revealed && (
        <div className={`answer-bar ${selected ? 'locked' : ''}`}>
          <button className={`answer-btn forgot ${selected === 'forgot' ? 'selected' : ''}`} onClick={() => handle(1, 'forgot')} disabled={!!selected}>
            <span className="icon">✕</span>
            <span className="answer-label">{t('review.forgot')}</span>
            <span className="answer-hint">{t('review.forgot_hint')}</span>
          </button>
          <button className={`answer-btn hard ${selected === 'hard' ? 'selected' : ''}`} onClick={() => handle(3, 'hard')} disabled={!!selected}>
            <span className="icon">◐</span>
            <span className="answer-label">{t('review.hard')}</span>
            <span className="answer-hint">{t('review.hard_hint')}</span>
          </button>
          <button className={`answer-btn easy ${selected === 'easy' ? 'selected' : ''}`} onClick={() => handle(5, 'easy')} disabled={!!selected}>
            <span className="icon">✓</span>
            <span className="answer-label">{t('review.easy')}</span>
            <span className="answer-hint">{t('review.easy_hint')}</span>
          </button>
        </div>
      )}
    </>
  );
}

function QuizMode({ current, pool, onAnswer, t, lang }) {
  const [picked, setPicked] = useState(null);

  const options = useMemo(() => {
    const distractors = pickDistractors(pool, current, 3);
    const all = [
      { id: current.id, text: current.translation, correct: true },
      ...distractors.map(w => ({ id: w.id, text: w.translation, correct: false })),
    ];
    // shuffle
    for (let i = all.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [all[i], all[j]] = [all[j], all[i]];
    }
    return all;
    // Freeze options per question (keyed remount handles new questions). Was
    // also on pool.length → the async getWords() pool swap reshuffled the
    // answers mid-question, moving the buttons under the user's finger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.id]);

  const handle = (opt) => {
    if (picked) return;
    setPicked(opt);
    onAnswer(opt.correct ? 5 : 1);
  };

  return (
    <div className="review-card">
      {current.image_url
        ? <img key={current.id} src={optimizeImage(current.image_url)} alt="" className="review-image" />
        : <WordPlaceholder word={current.word} className="review-image" />}
      <div className="review-pos">{current.part_of_speech || ''}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center' }}>
        <div className="review-word">{current.word}</div>
        <SpeakButton text={current.word} lang={current.target_lang} size="md" />
      </div>

      <div className="quiz-prompt">{t('review.quiz.prompt')} {FLAGS[lang] || ''}</div>

      <div className="quiz-options">
        {options.map(opt => {
          let cls = 'quiz-option';
          if (picked) {
            if (opt.correct) cls += ' correct';
            else if (opt.id === picked.id) cls += ' wrong';
            else cls += ' dim';
          }
          return (
            <button
              key={opt.id}
              className={cls}
              disabled={!!picked}
              onClick={() => handle(opt)}
              type="button"
            >
              {opt.text}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SpellingMode({ current, onAnswer, t, lang }) {
  const [value, setValue] = useState('');
  const [submitted, setSubmitted] = useState(null); // null | { correct: bool }
  const inputRef = useRef(null);

  useEffect(() => {
    setValue('');
    setSubmitted(null);
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [current.id]);

  const submit = (e) => {
    e?.preventDefault();
    if (submitted) return;
    const correct = normalize(value) === normalize(current.word);
    setSubmitted({ correct });
    onAnswer(correct ? 5 : 1);
  };

  const exampleSentence = (() => {
    const ex = current.examples;
    if (!ex || !ex.length) return null;
    const first = ex[0];
    return typeof first === 'string' ? first : first?.sentence;
  })();

  return (
    <div className="review-card">
      {current.image_url
        ? <img key={current.id} src={optimizeImage(current.image_url)} alt="" className="review-image" />
        : <WordPlaceholder word={current.word} className="review-image" />}
      <div className="review-pos">{current.part_of_speech || ''}</div>
      <div className="spelling-prompt">
        <div className="translation-eyebrow">{t('review.spelling.prompt')}</div>
        <div className="spelling-translation">{FLAGS[lang] || ''} {current.translation}</div>
      </div>

      <form onSubmit={submit} style={{ width: '100%' }}>
        <input
          ref={inputRef}
          className={`spelling-input ${submitted ? (submitted.correct ? 'correct' : 'wrong') : ''}`}
          value={value}
          onChange={e => setValue(e.target.value)}
          placeholder={t('review.spelling.placeholder')}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          disabled={!!submitted}
        />
        {!submitted ? (
          <button type="submit" className="btn btn-primary spelling-submit" disabled={!value.trim()}>
            {t('review.spelling.check')}
          </button>
        ) : (
          <div className={`spelling-feedback ${submitted.correct ? 'correct' : 'wrong'}`}>
            {submitted.correct ? `✓ ${t('review.spelling.correct')}` : (
              <>
                <div>✕ {t('review.spelling.wrong')}</div>
                <div className="spelling-answer">{current.word}</div>
              </>
            )}
            {exampleSentence && <div className="spelling-example">"{exampleSentence}"</div>}
          </div>
        )}
      </form>
    </div>
  );
}

export default ReviewPage;
