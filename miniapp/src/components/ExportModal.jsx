import { useState } from 'react';
import api from '../api/client';
import { useT } from '../contexts/LangContext';
import { track } from '../utils/analytics';

function ExportModal({ open, onClose, isPro }) {
  const { t } = useT();
  const [busy, setBusy] = useState(null); // 'csv' | 'apkg' | null
  const [error, setError] = useState('');
  const [done, setDone] = useState(null); // count exported

  if (!open) return null;

  const close = () => {
    setError('');
    setDone(null);
    setBusy(null);
    onClose?.();
  };

  const send = async (fmt) => {
    setBusy(fmt);
    setError('');
    setDone(null);
    track('export_clicked', { format: fmt });
    try {
      const r = await api.post('/api/export', null, { params: { format: fmt } });
      if (r.data?.ok) {
        setDone(r.data.word_count || 0);
      } else {
        setError(t('export.failed'));
      }
    } catch (e) {
      const status = e?.response?.status;
      if (status === 402) setError(t('export.pro_required'));
      else if (status === 400 && e?.response?.data?.detail === 'No words to export') {
        setError(t('export.no_words'));
      } else {
        setError(t('export.failed'));
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="day-modal-backdrop" onClick={close}>
      <div className="day-modal" onClick={(e) => e.stopPropagation()}>
        <div className="day-modal-emoji">📥</div>
        <h2 className="day-modal-title">{t('export.title')}</h2>
        <p className="day-modal-sub">{t('export.sub_chat')}</p>

        {done !== null ? (
          <>
            <div className="export-success">
              ✓ {t('export.sent', { n: done })}
            </div>
            <div className="day-modal-actions" style={{ marginTop: 14 }}>
              <button className="btn btn-gradient" onClick={close}>
                {t('export.close')}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="export-options">
              <button
                className="export-option"
                onClick={() => send('csv')}
                disabled={!!busy}
              >
                <div className="export-option-head">
                  <span className="export-option-name">CSV</span>
                  <span className="badge badge-new">{busy === 'csv' ? '…' : t('export.free')}</span>
                </div>
                <div className="export-option-desc">{t('export.csv_desc')}</div>
              </button>

              <button
                className="export-option"
                onClick={() => send('apkg')}
                disabled={!!busy || !isPro}
              >
                <div className="export-option-head">
                  <span className="export-option-name">Anki .apkg</span>
                  <span className="badge badge-mastered">
                    {busy === 'apkg' ? '…' : (isPro ? '✓ Pro' : '🔒 Pro')}
                  </span>
                </div>
                <div className="export-option-desc">{t('export.apkg_desc')}</div>
              </button>
            </div>

            {error && <div className="snap-error" style={{ marginTop: 12 }}>{error}</div>}

            <div className="day-modal-actions" style={{ marginTop: 14 }}>
              <button className="btn btn-ghost" onClick={close} disabled={!!busy}>
                {t('export.close')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default ExportModal;
