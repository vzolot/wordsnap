import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { clearCache, getStats, readCache, updateSettings, writeCache } from '../api/client';
import { useT, useLang } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import { track } from '../utils/analytics';

const LANGS = [
  { code: 'uk', flag: '🇺🇦', name: 'Українська' },
  { code: 'en', flag: '🇬🇧', name: 'English' },
  { code: 'es', flag: '🇪🇸', name: 'Español' },
  { code: 'pl', flag: '🇵🇱', name: 'Polski' },
  { code: 'de', flag: '🇩🇪', name: 'Deutsch' },
];

const TIMEZONES = [
  'Europe/Kiev', 'Europe/Warsaw', 'Europe/Berlin', 'Europe/Madrid',
  'Europe/London', 'Europe/Lisbon', 'Europe/Vilnius', 'Europe/Prague',
  'Europe/Vienna', 'Europe/Amsterdam', 'America/New_York', 'America/Los_Angeles',
];

const AVATARS = [
  '🐱','🐶','🦊','🐼','🐰','🐨','🐯','🦁',
  '🐮','🐷','🐸','🐵','🐔','🐧','🦉','🦅',
  '🦄','🐲','🦋','🐢','🦖','🐬','🐳','🦜',
  '🐝','🐞','🦂','🦑','🦐','🐍','🦔','🦦',
];

function SettingsPage() {
  const cached = readCache('stats', { ignoreTtl: true });
  const [stats, setStats] = useState(cached);
  const [saving, setSaving] = useState(null); // 'native_lang' | 'target_lang' | etc
  const [toast, setToast] = useState('');
  const navigate = useNavigate();
  const { t } = useT();
  const { setLang } = useLang();

  useEffect(() => {
    getStats().then(r => {
      setStats(r.data);
      writeCache('stats', r.data);
    }).catch(() => {});
  }, []);

  const apply = async (patch, fieldKey) => {
    setSaving(fieldKey);
    try {
      await updateSettings(patch);
      // Оптимістичне оновлення локального state
      setStats(s => ({ ...s, ...patch }));
      const cachedStats = readCache('stats', { ignoreTtl: true }) || {};
      writeCache('stats', { ...cachedStats, ...patch });
      // native_lang впливає на UI мову одразу
      if (patch.native_lang) setLang(patch.native_lang);
      track('settings_updated', { fields: Object.keys(patch) });
      // Прибираємо кеш по сторінках що залежать від мови
      clearCache('songs'); clearCache('themes');
      setToast(t('settings.saved'));
      setTimeout(() => setToast(''), 1800);
    } catch {
      setToast(t('settings.save_error'));
      setTimeout(() => setToast(''), 2400);
    } finally {
      setSaving(null);
    }
  };

  const native = stats?.native_lang || 'uk';
  const target = stats?.target_lang || null;
  const remindersEnabled = stats?.reminders_enabled !== false;
  const tz = stats?.timezone || 'Europe/Kiev';
  const avatar = stats?.avatar_emoji || null;

  return (
    <>
      <AppBar showProLink={false} />

      <div className="page">
        <h1 className="h1" style={{ marginBottom: 16 }}>{t('settings.title')}</h1>

        <div className="settings-section">
          <div className="settings-section-title">{t('settings.avatar')}</div>
          <div className="settings-section-sub">{t('settings.avatar_sub')}</div>
          <div className="settings-avatar-grid">
            {AVATARS.map(em => (
              <button
                key={em}
                className={`settings-avatar-btn ${avatar === em ? 'active' : ''}`}
                disabled={saving === 'avatar_emoji'}
                onClick={() => avatar !== em && apply({ avatar_emoji: em }, 'avatar_emoji')}
                type="button"
                aria-label={`Avatar ${em}`}
              >
                {em}
              </button>
            ))}
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">{t('settings.native_lang')}</div>
          <div className="settings-section-sub">{t('settings.native_lang_sub')}</div>
          <div className="settings-lang-grid">
            {LANGS.map(l => (
              <button
                key={l.code}
                className={`settings-lang-btn ${native === l.code ? 'active' : ''}`}
                disabled={saving === 'native_lang'}
                onClick={() => native !== l.code && apply({ native_lang: l.code }, 'native_lang')}
                type="button"
              >
                <span className="settings-lang-flag">{l.flag}</span>
                <span className="settings-lang-name">{l.name}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">{t('settings.target_lang')}</div>
          <div className="settings-section-sub">{t('settings.target_lang_sub')}</div>
          <div className="settings-lang-grid">
            {LANGS.map(l => (
              <button
                key={l.code}
                className={`settings-lang-btn ${target === l.code ? 'active' : ''}`}
                disabled={saving === 'target_lang'}
                onClick={() => target !== l.code && apply({ target_lang: l.code }, 'target_lang')}
                type="button"
              >
                <span className="settings-lang-flag">{l.flag}</span>
                <span className="settings-lang-name">{l.name}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-row">
            <div>
              <div className="settings-section-title">{t('settings.reminders')}</div>
              <div className="settings-section-sub">{t('settings.reminders_sub')}</div>
            </div>
            <button
              className={`settings-switch ${remindersEnabled ? 'on' : ''}`}
              disabled={saving === 'reminders_enabled'}
              onClick={() => apply({ reminders_enabled: !remindersEnabled }, 'reminders_enabled')}
              type="button"
              aria-pressed={remindersEnabled}
            >
              <span className="settings-switch-knob" />
            </button>
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">{t('settings.timezone')}</div>
          <div className="settings-section-sub">{t('settings.timezone_sub')}</div>
          <select
            className="settings-select"
            value={tz}
            disabled={saving === 'timezone'}
            onChange={(e) => apply({ timezone: e.target.value }, 'timezone')}
          >
            {TIMEZONES.map(z => (
              <option key={z} value={z}>{z.replace('_', ' ')}</option>
            ))}
          </select>
        </div>

        <button className="btn btn-secondary" style={{ marginTop: 12 }} onClick={() => navigate(-1)}>
          {t('settings.back')}
        </button>

        {toast && <div className="settings-toast">{toast}</div>}
      </div>
    </>
  );
}

export default SettingsPage;
