import { useState, useEffect } from 'react';
import { getTelegramUserId } from '../api/client';

function DebugBanner() {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 500);
    return () => clearInterval(id);
  }, []);

  const tg = window.Telegram?.WebApp;
  const userId = getTelegramUserId();

  if (userId) return null;

  const initDataLen = tg?.initData?.length || 0;
  const hasUser = !!tg?.initDataUnsafe?.user;
  const langCode = tg?.initDataUnsafe?.user?.language_code || '—';
  const platform = tg?.platform || '—';
  const version = tg?.version || '—';

  return (
    <div className="debug-banner">
      <b>⚠️ Telegram user not detected (check {tick})</b>
      <br />tg: {tg ? '✓' : '✗'} | initData: {initDataLen} chars | user: {hasUser ? '✓' : '✗'}
      <br />lang: {langCode} | platform: {platform} | v{version}
      <button onClick={() => window.location.reload()}>Reload</button>
    </div>
  );
}

export default DebugBanner;
