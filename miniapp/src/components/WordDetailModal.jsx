import { useState } from 'react';
import { deleteWord } from '../api/client';
import { useT } from '../contexts/LangContext';
import { optimizeImage } from '../utils/optimizeImage';
import SpeakButton from './SpeakButton';
import WordPlaceholder from './WordPlaceholder';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱', de: '🇩🇪', fr: '🇫🇷' };

function badgeClass(word) {
  if (word.status === 'mastered') return 'badge-mastered';
  if ((word.review_count || 0) === 0) return 'badge-new';
  return 'badge-learning';
}

function badgeLabel(word, t) {
  if (word.status === 'mastered') return t('badge.mastered');
  if ((word.review_count || 0) === 0) return t('badge.new');
  return t('badge.learning');
}

function WordDetailModal({ open, word, onClose, onDeleted, nativeLang }) {
  const { t } = useT();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (!open || !word) return null;
  const flag = FLAGS[nativeLang] || '🌐';
  const examples = Array.isArray(word.examples)
    ? word.examples.map(e => typeof e === 'string' ? { sentence: e, explanation: '' } : e)
    : [];

  const handleDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await deleteWord(word.id);
      onDeleted?.(word.id);
    } catch {
      setDeleting(false);
      // Залишаємо confirming щоб юзер міг повторити чи закрити
    }
  };

  const reset = () => { setConfirming(false); setDeleting(false); };
  const closeAndReset = () => { reset(); onClose?.(); };

  return (
    <div className="day-modal-backdrop" onClick={closeAndReset}>
      <div className="day-modal word-detail-modal" onClick={(e) => e.stopPropagation()}>
        {word.image_url ? (
          <img src={optimizeImage(word.image_url)} alt="" className="word-detail-img" loading="lazy" />
        ) : (
          <WordPlaceholder word={word.word} className="word-detail-img" />
        )}

        <div className="word-detail-meta">
          {word.part_of_speech && <span>{word.part_of_speech}</span>}
          {word.part_of_speech && word.difficulty && <span className="dot">·</span>}
          {word.difficulty && <span>{word.difficulty}</span>}
        </div>

        <div className="word-detail-word-row">
          <div className="word-detail-word">{word.word}</div>
          <SpeakButton text={word.word} lang={word.target_lang} size="md" />
        </div>
        <div className="word-detail-translation">{flag} {word.translation}</div>

        <div className="word-detail-status-row">
          <span className={`badge ${badgeClass(word)}`}>{badgeLabel(word, t)}</span>
          <span className="word-detail-review-count">
            {t('word_detail.reviews_n', { n: word.review_count || 0 })}
          </span>
        </div>

        {examples.length > 0 && (
          <>
            <div className="snap-section-label" style={{ textAlign: 'left' }}>{t('snap.examples')}</div>
            {examples.slice(0, 3).map((ex, i) => (
              <div key={i} className="snap-example-item">
                <span className="snap-example-num">{i + 1}.</span>
                <span className="snap-example-sentence">{ex.sentence}</span>
                {ex.explanation && (
                  <span className="snap-example-explanation">→ {ex.explanation}</span>
                )}
              </div>
            ))}
          </>
        )}

        {word.memory_tip && (
          <div className="snap-tip" style={{ textAlign: 'left' }}>
            💡 <span>{word.memory_tip}</span>
          </div>
        )}

        <div className="day-modal-actions" style={{ marginTop: 18 }}>
          {!confirming ? (
            <>
              <button className="btn btn-gradient" onClick={() => setConfirming(true)}>
                🗑 {t('word_detail.delete')}
              </button>
              <button className="btn btn-ghost" onClick={closeAndReset}>
                {t('word_detail.close')}
              </button>
            </>
          ) : (
            <>
              <button className="btn btn-gradient" disabled={deleting} onClick={handleDelete}>
                {deleting ? '…' : t('word_detail.delete_confirm')}
              </button>
              <button className="btn btn-ghost" disabled={deleting} onClick={() => setConfirming(false)}>
                {t('word_detail.cancel')}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default WordDetailModal;
