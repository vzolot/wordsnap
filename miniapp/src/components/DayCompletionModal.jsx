import { useT } from '../contexts/LangContext';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱', de: '🇩🇪', fr: '🇫🇷' };

// Повноекранна вітальна модалка коли юзер додав 10/10 слів за день.
// Показується один раз на день – повторне відкриття не тригерить.
function DayCompletionModal({
  open,
  onClose,
  onOpenReview,
  todayWords = [],
  streak,
  dueCount,
  dailyLimit,
  nativeLang,
}) {
  const { t } = useT();
  if (!open) return null;
  const flag = FLAGS[nativeLang] || '🌐';

  return (
    <div className="day-modal-backdrop" onClick={onClose}>
      <div className="day-modal" onClick={(e) => e.stopPropagation()}>
        <div className="day-modal-emoji">🎉</div>
        <h2 className="day-modal-title">{t('day_done.title')}</h2>
        <p className="day-modal-sub">
          {t('day_done.sub', { n: dailyLimit })}
        </p>

        <div className="day-modal-streak">
          <span className="day-modal-streak-icon">🔥</span>
          <span className="day-modal-streak-num">{streak}</span>
          <span className="day-modal-streak-label">{t('day_done.streak_days')}</span>
        </div>

        {todayWords.length > 0 && (
          <>
            <div className="day-modal-list-label">{t('day_done.added_today')}</div>
            <div className="day-modal-list">
              {todayWords.map(w => (
                <div key={w.id} className="day-modal-row">
                  <span className="day-modal-row-word">{w.word}</span>
                  <span className="day-modal-row-translation">{flag} {w.translation}</span>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="day-modal-actions">
          {dueCount > 0 && (
            <button className="btn btn-gradient" onClick={onOpenReview}>
              {t('day_done.cta_review', { n: dueCount })}
            </button>
          )}
          <button className="btn btn-ghost" onClick={onClose}>
            {t('day_done.cta_close')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default DayCompletionModal;
