import { useCallback, useEffect, useState } from 'react';
import AppBar from '../components/AppBar';
import {
  getCalendarSlots, getMyLessons, bookLesson, cancelMyLesson,
} from '../api/client';

const WD = ['Нд', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

function fmtDay(iso) {
  const d = new Date(iso);
  return `${WD[d.getDay()]}, ${d.getDate().toString().padStart(2, '0')}.${(d.getMonth() + 1).toString().padStart(2, '0')}`;
}
function fmtTime(iso) {
  const d = new Date(iso);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}
function fmtFull(iso) {
  return `${fmtDay(iso)} ${fmtTime(iso)}`;
}

export default function LessonsPage() {
  const [slots, setSlots] = useState(null);
  const [mine, setMine] = useState([]);
  const [hasTeacher, setHasTeacher] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const [sl, my] = await Promise.all([getCalendarSlots(), getMyLessons()]);
    setSlots(sl.data.slots || []);
    setHasTeacher(sl.data.has_teacher !== false);
    setMine(my.data.lessons || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const book = async (iso) => {
    setBusy(true); setMsg('');
    try {
      await bookLesson(iso);
      setMsg('Урок заброньовано ✅');
      await load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setMsg(d === 'slot_taken' ? 'Цей слот щойно зайняли, оберіть інший.'
        : d === 'slot_unavailable' ? 'Слот більше недоступний.'
        : 'Не вдалося забронювати.');
    } finally { setBusy(false); }
  };

  const cancel = async (id) => {
    setBusy(true); setMsg('');
    try {
      await cancelMyLesson(id);
      setMsg('Урок скасовано.');
      await load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setMsg(d === 'too_late' ? 'Скасувати вже пізно (менш ніж за 12 год).' : 'Не вдалося скасувати.');
    } finally { setBusy(false); }
  };

  // групуємо вільні слоти по локальному дню
  const byDay = {};
  (slots || []).forEach((s) => {
    const k = fmtDay(s.local);
    (byDay[k] = byDay[k] || []).push(s);
  });

  return (
    <div className="page">
      <AppBar showProLink={false} />
      <div className="tch-wrap">
        <h2 className="tch-title">Уроки</h2>
        {msg && <p className="tch-ok">{msg}</p>}

        {mine.length > 0 && (
          <div className="tch-card">
            <h3 className="tch-h3">Мої майбутні уроки</h3>
            {mine.map((l) => (
              <div key={l.id} className="tch-word">
                <span>📅 <b>{fmtFull(l.starts_at_utc)}</b></span>
                <button className="tch-btn ghost sm" onClick={() => cancel(l.id)} disabled={busy}>Скасувати</button>
              </div>
            ))}
          </div>
        )}

        <div className="tch-card">
          <h3 className="tch-h3">Вільні слоти</h3>
          {slots === null && <p className="tch-muted">Завантаження…</p>}
          {slots && !hasTeacher && <p className="tch-muted">Викладач ще не налаштував розклад.</p>}
          {slots && hasTeacher && slots.length === 0 && (
            <p className="tch-muted">Наразі вільних слотів немає. Загляньте пізніше.</p>
          )}
          {Object.entries(byDay).map(([day, list]) => (
            <div key={day} className="tch-slotday">
              <div className="tch-slotday-h">{day}</div>
              <div className="tch-slotgrid">
                {list.map((s) => (
                  <button key={s.starts_at_utc} className="tch-slot"
                          onClick={() => book(s.starts_at_utc)} disabled={busy}>
                    {fmtTime(s.local)}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="tch-muted sm">Час показано у твоєму часовому поясі. Змінити — у Налаштуваннях.</p>
      </div>
    </div>
  );
}
