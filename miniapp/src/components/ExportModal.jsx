import { useState } from 'react';
import { getTelegramUserId } from '../api/client';
import { useT } from '../contexts/LangContext';
import { track } from '../utils/analytics';

const API_URL = import.meta.env.VITE_API_URL || 'https://worker-production-abd5.up.railway.app';

function ExportModal({ open, onClose, isPro }) {
  const { t } = useT();
  const [busy, setBusy] = useState(null); // 'csv' | 'apkg' | null
  const [error, setError] = useState('');

  if (!open) return null;

  const download = async (fmt) => {
    setBusy(fmt);
    setError('');
    track('export_clicked', { format: fmt });
    try {
      const tid = getTelegramUserId();
      const url = `${API_URL}/api/export?format=${fmt}&telegram_id=${tid}`;
      const res = await fetch(url);
      if (res.status === 402) { setError(t('export.pro_required')); return; }
      if (!res.ok) { setError(t('export.failed')); return; }
      const blob = await res.blob();
      // На iOS Telegram WebView download через <a> працює нестабільно — даємо
      // оновлений URL через openLink, юзер отримає файл у системному браузері.
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = `wordsnap.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objUrl), 5000);
    } catch (e) {
      setError(t('export.failed'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="day-modal-backdrop" onClick={onClose}>
      <div className="day-modal" onClick={(e) => e.stopPropagation()}>
        <div className="day-modal-emoji">📥</div>
        <h2 className="day-modal-title">{t('export.title')}</h2>
        <p className="day-modal-sub">{t('export.sub')}</p>

        <div className="export-options">
          <button
            className="export-option"
            onClick={() => download('csv')}
            disabled={busy === 'csv'}
          >
            <div className="export-option-head">
              <span className="export-option-name">CSV</span>
              <span className="badge badge-new">{t('export.free')}</span>
            </div>
            <div className="export-option-desc">{t('export.csv_desc')}</div>
          </button>

          <button
            className="export-option"
            onClick={() => download('apkg')}
            disabled={busy === 'apkg' || !isPro}
          >
            <div className="export-option-head">
              <span className="export-option-name">Anki .apkg</span>
              <span className="badge badge-mastered">{isPro ? '✓ Pro' : '🔒 Pro'}</span>
            </div>
            <div className="export-option-desc">{t('export.apkg_desc')}</div>
          </button>
        </div>

        {error && <div className="snap-error" style={{ marginTop: 12 }}>{error}</div>}

        <div className="day-modal-actions" style={{ marginTop: 14 }}>
          <button className="btn btn-ghost" onClick={onClose}>
            {t('export.close')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ExportModal;
