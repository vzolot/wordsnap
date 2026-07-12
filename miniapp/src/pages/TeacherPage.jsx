import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AppBar from '../components/AppBar';
import { useTenant } from '../contexts/TenantContext';
import { useRole } from '../contexts/RoleContext';
import {
  getTeacherDecks, getTeacherStudents, getTeacherDeck,
  createTeacherDeck, updateTeacherDeck, getTeacherStudentDetail,
  getAvailability, putAvailability, getTeacherLessons, teacherCancelLesson,
  teacherCreateLesson,
  createDeckFromPhoto, assignHomework,
  getSchoolInfo, getTeachers, addTeacher, setTeacherActive,
  getGroups, createGroup, setGroupMembers,
} from '../api/client';

// ── Спільні хелпери для «поділитися ботом» ────────────────────────────────
function botLink(username) {
  return `https://t.me/${(username || 'WordSnapBot').replace(/^@/, '')}`;
}
function shareBot(username) {
  const url = botLink(username);
  const text = 'Приєднуйся — вчимо слова разом 📚';
  const tg = window.Telegram?.WebApp;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
  if (tg?.openTelegramLink) tg.openTelegramLink(shareUrl);
  else window.open(shareUrl, '_blank');
}

function ShareBotButton({ block }) {
  const { bot_username } = useTenant();
  return (
    <button
      className={`tch-btn${block ? '' : ' sm'}`}
      style={block ? { width: '100%', marginTop: 10 } : undefined}
      onClick={() => shareBot(bot_username)}
    >
      🔗 Поділитися ботом
    </button>
  );
}

// Рейтинг усіх учнів тенанта за сумарним XP (замість тижневого топу повторень).
function StudentRanking({ students }) {
  if (!students || students.length === 0) return null;
  const ranked = [...students].sort((a, b) => (b.total_xp || 0) - (a.total_xp || 0));
  const medals = ['🥇', '🥈', '🥉'];
  return (
    <div className="tch-card">
      <h3 className="tch-h3">🏆 Рейтинг за XP</h3>
      {ranked.map((s, i) => (
        <div key={s.id} className="tch-word">
          <span>{medals[i] || `${i + 1}.`} <b>{s.display_name}</b></span>
          <span className="tch-muted">{s.total_xp || 0} XP</span>
        </div>
      ))}
    </div>
  );
}

// Читає File як base64 без data-URL префіксу + повертає mime.
function fileToB64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = String(r.result);
      resolve({ b64: s.slice(s.indexOf(',') + 1), mime: file.type || 'image/jpeg' });
    };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд'];
const toMin = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };
const toHHMM = (min) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;
// Дропдаун часу: 00:00…23:30 кроком 30 хв (замість нативного time-інпуту).
const TIME_OPTIONS = Array.from({ length: 48 }, (_, i) => toHHMM(i * 30));
function TimeSelect({ value, onChange }) {
  return (
    <select className="tch-time" value={value} onChange={(e) => onChange(e.target.value)}>
      {TIME_OPTIONS.map((tt) => <option key={tt} value={tt}>{tt}</option>)}
    </select>
  );
}
const _WD_SHORT = ['Нд', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const dayLabel = (d) => `${_WD_SHORT[d.getDay()]}, ${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
const hhmmLocal = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;

function CalendarManager() {
  // ranges: { [weekday]: [{start,end}] }  (HH:MM рядки)
  const [ranges, setRanges] = useState({});
  const [tz, setTz] = useState('');
  const [lessons, setLessons] = useState([]);
  const [students, setStudents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  // Форма ручного бронювання уроку викладачем.
  const [bkStudent, setBkStudent] = useState('');
  const [bkDate, setBkDate] = useState('');
  const [bkTime, setBkTime] = useState('12:00');
  const [bkMsg, setBkMsg] = useState('');

  const load = useCallback(async () => {
    const [a, l, st] = await Promise.all([
      getAvailability(), getTeacherLessons(), getTeacherStudents(),
    ]);
    const r = {};
    (a.data.availability || []).forEach((s) => {
      (r[s.weekday] = r[s.weekday] || []).push({ start: toHHMM(s.start_min), end: toHHMM(s.end_min) });
    });
    setRanges(r);
    setTz(a.data.timezone);
    setLessons(l.data.lessons || []);
    setStudents(st.data.students || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const addRange = (wd) => setRanges((p) => ({ ...p, [wd]: [...(p[wd] || []), { start: '10:00', end: '11:00' }] }));
  const rmRange = (wd, i) => setRanges((p) => ({ ...p, [wd]: p[wd].filter((_, j) => j !== i) }));
  const setField = (wd, i, k, v) => setRanges((p) => ({
    ...p, [wd]: p[wd].map((r, j) => (j === i ? { ...r, [k]: v } : r)),
  }));

  const save = async () => {
    setBusy(true); setMsg('');
    const slots = [];
    Object.entries(ranges).forEach(([wd, list]) => {
      list.forEach((r) => {
        const sm = toMin(r.start), em = toMin(r.end);
        if (em > sm) slots.push({ weekday: Number(wd), start_min: sm, end_min: em });
      });
    });
    try {
      await putAvailability(slots);
      setMsg('Збережено ✅');
    } catch { setMsg('Не вдалося зберегти.'); }
    finally { setBusy(false); }
  };

  const cancelLesson = async (id) => {
    setBusy(true);
    try { await teacherCancelLesson(id); await load(); } finally { setBusy(false); }
  };

  const book = async () => {
    if (!bkStudent || !bkDate || !bkTime) { setBkMsg('Оберіть учня, дату і час.'); return; }
    setBusy(true); setBkMsg('');
    try {
      // Дата+час у локальному поясі пристрою (= пояс викладача) → UTC ISO.
      const iso = new Date(`${bkDate}T${bkTime}:00`).toISOString();
      await teacherCreateLesson(Number(bkStudent), iso);
      setBkMsg('Урок додано ✅');
      setBkDate('');
      await load();
    } catch (e) {
      const err = e?.response?.data?.detail;
      setBkMsg(err === 'slot_taken' ? 'Цей час уже зайнятий.' : 'Не вдалося додати урок.');
    } finally { setBusy(false); }
  };

  // Денний розклад: групуємо заброньовані уроки за локальною датою.
  const byDay = [];
  const _map = new Map();
  [...lessons]
    .sort((a, b) => new Date(a.starts_at_utc) - new Date(b.starts_at_utc))
    .forEach((l) => {
      const d = new Date(l.starts_at_utc);
      const key = dayKey(d);
      if (!_map.has(key)) { const g = { label: dayLabel(d), items: [] }; _map.set(key, g); byDay.push(g); }
      _map.get(key).items.push(l);
    });

  return (
    <>
      {/* 1. Вільні години — інтервали, з яких учні самі бронюють. Дропдауни. */}
      <div className="tch-card">
        <h3 className="tch-h3">Вільні години</h3>
        <p className="tch-muted sm">
          Пояс: {tz || '—'} · тривалість слота = тривалість уроку. Учні бачать ці інтервали для самостійного запису.
        </p>
        {WEEKDAYS.map((name, wd) => (
          <div key={wd} className="tch-wdrow">
            <div className="tch-wd">{name}</div>
            <div className="tch-wdranges">
              {(ranges[wd] || []).map((r, i) => (
                <div key={i} className="tch-range">
                  <TimeSelect value={r.start} onChange={(v) => setField(wd, i, 'start', v)} />
                  <span>–</span>
                  <TimeSelect value={r.end} onChange={(v) => setField(wd, i, 'end', v)} />
                  <button className="tch-x" onClick={() => rmRange(wd, i)}>✕</button>
                </div>
              ))}
              <button className="tch-addrange" onClick={() => addRange(wd)}>+ інтервал</button>
            </div>
          </div>
        ))}
        {msg && <p className="tch-ok">{msg}</p>}
        <div className="tch-actions">
          <button className="tch-btn" onClick={save} disabled={busy}>Зберегти вільні години</button>
        </div>
      </div>

      {/* 2. Ручне бронювання уроку викладачем (окремо від вільних годин). */}
      <div className="tch-card">
        <h3 className="tch-h3">Забронювати урок вручну</h3>
        {students.length === 0 ? (
          <p className="tch-muted sm">Спершу додайте учнів — тоді зможете ставити їм уроки.</p>
        ) : (
          <>
            <div className="tch-book">
              <select className="tch-time grow" value={bkStudent} onChange={(e) => setBkStudent(e.target.value)}>
                <option value="">Учень…</option>
                {students.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
              </select>
              <input type="date" className="tch-time" value={bkDate} onChange={(e) => setBkDate(e.target.value)} />
              <TimeSelect value={bkTime} onChange={setBkTime} />
            </div>
            {bkMsg && <p className="tch-ok">{bkMsg}</p>}
            <div className="tch-actions">
              <button className="tch-btn" onClick={book} disabled={busy}>Забронювати</button>
            </div>
          </>
        )}
      </div>

      {/* 3. Денний розклад: хто і о котрій. */}
      <div className="tch-card">
        <h3 className="tch-h3">Розклад</h3>
        {byDay.length === 0 && <p className="tch-muted">Поки що немає бронювань.</p>}
        {byDay.map((day) => (
          <div key={day.label} className="tch-day">
            <div className="tch-day-h">{day.label}</div>
            {day.items.map((l) => (
              <div key={l.id} className="tch-word">
                <span>🕑 <b>{hhmmLocal(new Date(l.starts_at_utc))}</b> — {l.student_name || 'учень'}</span>
                <button className="tch-btn ghost sm" onClick={() => cancelLesson(l.id)} disabled={busy}>Скасувати</button>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

function relTime(iso) {
  if (!iso) return 'ніколи не заходив';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return 'сьогодні';
  if (days === 1) return 'вчора';
  if (days < 7) return `${days} дн. тому`;
  if (days < 30) return `${Math.floor(days / 7)} тижн. тому`;
  return `${Math.floor(days / 30)} міс. тому`;
}

// Режим викладача (white-label M5). Текст українською — аудиторія викладачів
// україномовна діаспора (узгоджено з ТЗ; повний i18n — за потреби пізніше).

function StudentPicker({ students, selected, onToggle }) {
  return (
    <div className="tch-students">
      {students.map((s) => (
        <label key={s.id} className="tch-student">
          <input
            type="checkbox"
            checked={selected.has(s.id)}
            onChange={() => onToggle(s.id)}
          />
          <span>{s.display_name || s.first_name || `id${s.telegram_id}`}</span>
        </label>
      ))}
      {students.length === 0 && (
        <p className="tch-muted">Ще немає учнів. Поділіться посиланням на бота.</p>
      )}
    </div>
  );
}

function CreateDeckForm({ students, onCreated, onCancel }) {
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [target, setTarget] = useState('all'); // all | selected | group
  const [selected, setSelected] = useState(new Set());
  const [groups, setGroups] = useState([]);
  const [groupId, setGroupId] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [photoBusy, setPhotoBusy] = useState(false);
  const assignAll = target === 'all';

  useEffect(() => { getGroups().then((r) => setGroups(r.data.groups || [])).catch(() => {}); }, []);

  const onPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setErr(''); setPhotoBusy(true);
    try {
      const { b64, mime } = await fileToB64(file);
      const r = await createDeckFromPhoto(b64, mime);
      const pairs = r.data.pairs || [];
      if (pairs.length === 0) { setErr('Не вдалося розпізнати слова на фото.'); return; }
      const lines = pairs.map((p) => `${p.word} - ${p.translation}`).join('\n');
      setText((prev) => (prev.trim() ? prev.trim() + '\n' : '') + lines);
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(d === 'ai_snap_limit_reached'
        ? 'Ліміт розпізнавання фото на цей місяць вичерпано. Доступно з наступного місяця.'
        : 'Не вдалося обробити фото.');
    } finally { setPhotoBusy(false); }
  };

  const toggle = (id) => setSelected((prev) => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const submit = async () => {
    setErr('');
    if (!title.trim()) { setErr('Вкажіть назву колоди'); return; }
    if (!text.trim()) { setErr('Додайте слова: «слово - переклад» по рядку'); return; }
    if (target === 'group' && !groupId) { setErr('Оберіть групу'); return; }
    setBusy(true);
    try {
      const r = await createTeacherDeck({
        title: title.trim(),
        text,
        assign_to_all: target === 'all',
        assignee_user_ids: target === 'selected' ? [...selected] : null,
        group_id: target === 'group' ? Number(groupId) : null,
      });
      onCreated(r.data);
    } catch (e) {
      setErr(e?.response?.data?.detail === 'no_valid_pairs'
        ? 'Не розпізнав жодної пари. Формат: «слово - переклад» по рядку.'
        : 'Не вдалося створити колоду. Спробуйте ще раз.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tch-card">
      <h3 className="tch-h3">Нова колода</h3>
      <input
        className="tch-input"
        placeholder="Назва колоди (напр. «Польська: побут»)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="tch-textarea"
        rows={8}
        placeholder={'Слова, по одному на рядок:\nдім - dom\nвода - woda\n\nАбо вставте CSV (2 колонки).'}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <label className="tch-photo-btn">
        {photoBusy ? '📷 Розпізнаю…' : '📷 Створити з фото'}
        <input type="file" accept="image/*" capture="environment"
               onChange={onPhoto} disabled={photoBusy} hidden />
      </label>
      <div className="tch-toggle-row">
        <button className={`tch-pill ${target === 'all' ? 'on' : ''}`}
                onClick={() => setTarget('all')}>Всім</button>
        <button className={`tch-pill ${target === 'selected' ? 'on' : ''}`}
                onClick={() => setTarget('selected')}>Обраним</button>
        {groups.length > 0 && (
          <button className={`tch-pill ${target === 'group' ? 'on' : ''}`}
                  onClick={() => setTarget('group')}>Групі</button>
        )}
      </div>
      {target === 'selected' && (
        <StudentPicker students={students} selected={selected} onToggle={toggle} />
      )}
      {target === 'group' && (
        <select className="tch-input" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">— оберіть групу —</option>
          {groups.map((g) => <option key={g.id} value={g.id}>{g.name} ({g.members})</option>)}
        </select>
      )}
      {err && <p className="tch-err">{err}</p>}
      <div className="tch-actions">
        <button className="tch-btn ghost" onClick={onCancel} disabled={busy}>Скасувати</button>
        <button className="tch-btn" onClick={submit} disabled={busy}>
          {busy ? 'Створюю…' : 'Створити колоду'}
        </button>
      </div>
    </div>
  );
}

function EditDeck({ deckId, students, onClose }) {
  const [deck, setDeck] = useState(null);
  const [addText, setAddText] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const r = await getTeacherDeck(deckId);
    setDeck(r.data);
  }, [deckId]);
  useEffect(() => { load(); }, [load]);

  const addWords = async () => {
    if (!addText.trim()) return;
    setBusy(true); setMsg('');
    try {
      const r = await updateTeacherDeck(deckId, { add_text: addText });
      setAddText('');
      setMsg(`Додано слів: ${r.data.added_words ?? 0}`);
      await load();
    } finally { setBusy(false); }
  };

  const removeWord = async (wid) => {
    setBusy(true);
    try {
      await updateTeacherDeck(deckId, { remove_word_ids: [wid] });
      await load();
    } finally { setBusy(false); }
  };

  if (!deck) return <div className="tch-card"><p className="tch-muted">Завантаження…</p></div>;

  return (
    <div className="tch-card">
      <div className="tch-edit-head">
        <h3 className="tch-h3">{deck.title}</h3>
        <button className="tch-btn ghost sm" onClick={onClose}>← Назад</button>
      </div>
      <p className="tch-muted">
        {deck.assign_to_all ? 'Призначена всім учням' : `Призначена обраним (${deck.assignee_user_ids.length})`}
        {' · '}{deck.words.length} слів
      </p>

      <div className="tch-wordlist">
        {deck.words.map((w) => (
          <div key={w.id} className="tch-word">
            <span><b>{w.word}</b> — {w.translation}</span>
            <button className="tch-x" onClick={() => removeWord(w.id)} disabled={busy} aria-label="Видалити">✕</button>
          </div>
        ))}
      </div>

      <h4 className="tch-h4">Додати слова</h4>
      <textarea
        className="tch-textarea"
        rows={4}
        placeholder={'нове слово - переклад'}
        value={addText}
        onChange={(e) => setAddText(e.target.value)}
      />
      {msg && <p className="tch-ok">{msg}</p>}
      <div className="tch-actions">
        <button className="tch-btn" onClick={addWords} disabled={busy}>
          {busy ? 'Зберігаю…' : 'Додати'}
        </button>
      </div>
      <p className="tch-muted sm">Нові слова підхопляться в учнів без скидання вивченого.</p>

      <h4 className="tch-h4">Домашнє завдання (дедлайн)</h4>
      <DeadlineAssign deckId={deckId} />
    </div>
  );
}

function DeadlineAssign({ deckId }) {
  const [due, setDue] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const assign = async () => {
    if (!due) { setMsg('Оберіть дату дедлайну.'); return; }
    setBusy(true); setMsg('');
    try {
      const iso = new Date(due).toISOString();
      const r = await assignHomework(deckId, iso);
      setMsg(`Дедлайн призначено ${r.data.assigned} учням ✅`);
    } catch { setMsg('Не вдалося призначити.'); }
    finally { setBusy(false); }
  };
  return (
    <div className="tch-range" style={{ flexWrap: 'wrap' }}>
      <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      <button className="tch-btn sm" onClick={assign} disabled={busy}>Призначити всім</button>
      {msg && <p className="tch-ok" style={{ width: '100%' }}>{msg}</p>}
    </div>
  );
}

function StudentDetail({ studentId, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    getTeacherStudentDetail(studentId).then((r) => setD(r.data)).catch(() => setErr(true));
  }, [studentId]);

  if (err) return <div className="tch-card"><p className="tch-muted">Не вдалося завантажити.</p></div>;
  if (!d) return <div className="tch-card"><p className="tch-muted">Завантаження…</p></div>;

  // Мінібар активності за 30 днів
  const today = new Date();
  const bars = [];
  let maxN = 1;
  for (let i = 29; i >= 0; i--) {
    const dt = new Date(today.getTime() - i * 86400000);
    const key = dt.toISOString().slice(0, 10);
    const n = d.activity[key] || 0;
    if (n > maxN) maxN = n;
    bars.push({ key, n });
  }

  return (
    <div className="tch-card">
      <div className="tch-edit-head">
        <h3 className="tch-h3">{d.display_name}</h3>
        <button className="tch-btn ghost sm" onClick={onClose}>← Назад</button>
      </div>
      <div className="tch-metrics">
        <div className="tch-metric"><b>{d.streak}</b><span>днів поспіль</span></div>
        <div className="tch-metric"><b>{d.reviews_7d}</b><span>за 7 днів</span></div>
        <div className="tch-metric"><b>{d.reviews_30d}</b><span>за 30 днів</span></div>
      </div>

      <h4 className="tch-h4">Активність (30 днів)</h4>
      <div className="tch-spark">
        {bars.map((b) => (
          <div key={b.key} className="tch-spark-bar"
               style={{ height: `${Math.max(3, Math.round(100 * b.n / maxN))}%` }}
               title={`${b.key}: ${b.n}`} />
        ))}
      </div>

      <h4 className="tch-h4">Прогрес по колодах</h4>
      {d.decks.length === 0 && <p className="tch-muted">Немає призначених колод.</p>}
      {d.decks.map((dk) => {
        const total = dk.learned + dk.in_progress + dk.not_started || 1;
        return (
          <div key={dk.deck_id} className="tch-deckprog">
            <div className="tch-deckprog-top">
              <span>{dk.title}</span>
              <span className="tch-muted">{dk.learned}/{total}</span>
            </div>
            <div className="tch-bar">
              <div className="tch-bar-learned" style={{ width: `${100 * dk.learned / total}%` }} />
              <div className="tch-bar-prog" style={{ width: `${100 * dk.in_progress / total}%` }} />
            </div>
          </div>
        );
      })}

      <h4 className="tch-h4">Слабкі слова</h4>
      {d.weak_words.length === 0 && <p className="tch-muted">Замало даних або немає помилок.</p>}
      {d.weak_words.map((w) => (
        <div key={w.word_id} className="tch-word">
          <span><b>{w.word}</b> — {w.translation}</span>
          <span className="tch-weak">{Math.round(w.error_rate * 100)}% помилок</span>
        </div>
      ))}
    </div>
  );
}

function StudentsList() {
  const [students, setStudents] = useState(null);
  const [sel, setSel] = useState(null);

  useEffect(() => {
    getTeacherStudents().then((r) => setStudents(r.data.students || [])).catch(() => setStudents([]));
  }, []);

  if (sel != null) return <StudentDetail studentId={sel} onClose={() => setSel(null)} />;
  if (students === null) return <p className="tch-muted">Завантаження…</p>;
  if (students.length === 0) return (
    <div className="tch-card">
      <p className="tch-muted">Ще немає учнів. Поділіться посиланням на бота, щоб вони приєдналися.</p>
      <ShareBotButton block />
    </div>
  );

  return (
    <>
      <StudentRanking students={students} />
      <div className="tch-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="tch-muted sm">{students.length} учнів</span>
        <ShareBotButton />
      </div>
      {students.map((s) => (
        <button key={s.id} className="tch-deck" onClick={() => setSel(s.id)}>
          <div className="tch-deck-main">
            <div className="tch-deck-title">
              {s.display_name}{s.at_risk && <span className="tch-risk">в ризику</span>}
            </div>
            <div className="tch-deck-sub">
              ⭐ {s.total_xp || 0} XP · 🔥 {s.streak} · {s.learned_pct}% вивчено · {relTime(s.last_visit)}
            </div>
          </div>
          <span className="tch-deck-edit">›</span>
        </button>
      ))}
    </>
  );
}

function GroupEditor({ group, students, onDone }) {
  const [sel, setSel] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const toggle = (id) => setSel((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const save = async () => {
    setBusy(true);
    try { await setGroupMembers(group.id, [...sel]); onDone(); } finally { setBusy(false); }
  };
  return (
    <div className="tch-card">
      <h4 className="tch-h4">Учні групи «{group.name}»</h4>
      <StudentPicker students={students} selected={sel} onToggle={toggle} />
      <div className="tch-actions">
        <button className="tch-btn ghost sm" onClick={onDone}>Назад</button>
        <button className="tch-btn sm" onClick={save} disabled={busy}>Зберегти склад</button>
      </div>
    </div>
  );
}

function SchoolManager() {
  const [info, setInfo] = useState(null);
  const [teachers, setTeachers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [students, setStudents] = useState([]);
  const [newTeacher, setNewTeacher] = useState('');
  const [newGroup, setNewGroup] = useState('');
  const [editGroup, setEditGroup] = useState(null);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const inf = (await getSchoolInfo()).data;
    setInfo(inf);
    const [g, s] = await Promise.all([getGroups(), getTeacherStudents()]);
    setGroups(g.data.groups || []);
    setStudents(s.data.students || []);
    if (inf.role === 'owner') setTeachers((await getTeachers()).data.teachers || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  if (!info) return <p className="tch-muted">Завантаження…</p>;
  if (!info.is_school) return <div className="tch-card"><p className="tch-muted">
    Це репетиторський тенант (не школа). Режим школи вмикає оператор.</p></div>;
  if (editGroup) return <GroupEditor group={editGroup} students={students}
    onDone={() => { setEditGroup(null); load(); }} />;

  const addT = async () => {
    setMsg('');
    try { await addTeacher(Number(newTeacher)); setNewTeacher(''); await load(); setMsg('Викладача додано ✅'); }
    catch (e) { setMsg(e?.response?.data?.detail === 'user_not_found' ? 'Спершу викладач має натиснути Start у боті.' : 'Помилка.'); }
  };
  const addG = async () => {
    if (!newGroup.trim()) return;
    await createGroup(newGroup.trim()); setNewGroup(''); await load();
  };

  return (
    <>
      {info.role === 'owner' && (
        <div className="tch-card">
          <h3 className="tch-h3">Викладачі</h3>
          {teachers.map((t) => (
            <div key={t.id} className="tch-word">
              <span>{t.name} · {t.role === 'owner' ? 'власник' : (t.is_active ? 'активний' : 'вимкнено')}</span>
              {t.role === 'teacher' && (
                <button className="tch-btn ghost sm" onClick={async () => { await setTeacherActive(t.id, !t.is_active); load(); }}>
                  {t.is_active ? 'Вимкнути' : 'Увімкнути'}
                </button>
              )}
            </div>
          ))}
          <div className="tch-range" style={{ flexWrap: 'wrap', marginTop: 8 }}>
            <input className="tch-input" style={{ flex: 1 }} placeholder="Telegram ID викладача"
                   value={newTeacher} onChange={(e) => setNewTeacher(e.target.value)} />
            <button className="tch-btn sm" onClick={addT}>Додати викладача</button>
          </div>
          {msg && <p className="tch-ok">{msg}</p>}
        </div>
      )}

      <div className="tch-card">
        <h3 className="tch-h3">Групи</h3>
        {groups.length === 0 && <p className="tch-muted">Ще немає груп.</p>}
        {groups.map((g) => (
          <div key={g.id} className="tch-word">
            <span>👥 <b>{g.name}</b> — {g.members} учнів</span>
            <button className="tch-btn ghost sm" onClick={() => setEditGroup(g)}>Склад</button>
          </div>
        ))}
        <div className="tch-range" style={{ flexWrap: 'wrap', marginTop: 8 }}>
          <input className="tch-input" style={{ flex: 1 }} placeholder="Назва групи (напр. «Польська B1»)"
                 value={newGroup} onChange={(e) => setNewGroup(e.target.value)} />
          <button className="tch-btn sm" onClick={addG}>Створити групу</button>
        </div>
      </div>
    </>
  );
}

function Kpi({ value, label, warn }) {
  return (
    <div className="tch-kpi">
      <div className={`tch-kpi-n${warn ? ' warn' : ''}`}>{value}</div>
      <div className="tch-kpi-l">{label}</div>
    </div>
  );
}

// Викладацька статистика: зведені KPI + детальний прогрес по ОБРАНИХ учнях
// (перевикористовує StudentPicker для вибору і StudentDetail для показу).
function TeacherStats({ students }) {
  const [sel, setSel] = useState(new Set());
  const toggle = (id) => setSel((prev) => {
    const n = new Set(prev);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });

  if (!students || students.length === 0) {
    return (
      <div className="tch-card">
        <p className="tch-muted">Статистика зʼявиться, коли приєднаються учні.</p>
      </div>
    );
  }

  const n = students.length;
  const active7 = students.filter((s) => (s.reviews_7d || 0) > 0).length;
  const atRisk = students.filter((s) => s.at_risk).length;
  const avgLearned = Math.round(students.reduce((a, s) => a + (s.learned_pct || 0), 0) / n);

  return (
    <>
      <div className="tch-kpis">
        <Kpi value={n} label="учнів" />
        <Kpi value={active7} label="активних 7д" />
        <Kpi value={atRisk} label="у ризику" warn={atRisk > 0} />
        <Kpi value={`${avgLearned}%`} label="сер. вивчено" />
      </div>

      <div className="tch-card">
        <h3 className="tch-h3">Статистика по учнях</h3>
        <p className="tch-muted sm">Оберіть учнів — нижче зʼявиться їхній детальний прогрес.</p>
        <StudentPicker students={students} selected={sel} onToggle={toggle} />
      </div>

      {[...sel].map((id) => (
        <StudentDetail key={id} studentId={id} onClose={() => toggle(id)} />
      ))}
    </>
  );
}

export default function TeacherPage() {
  // Активна вкладка — з URL (?tab=), щоб нижня викладацька навігація й
  // внутрішні пігулки були одним джерелом істини.
  const [sp, setSp] = useSearchParams();
  const view = sp.get('tab') || 'students'; // students | decks | calendar | stats | school
  const setView = (v) => setSp({ tab: v }, { replace: true });

  const { setStudentPreview } = useRole();
  const navigate = useNavigate();
  const previewAsStudent = () => { setStudentPreview(true); navigate('/'); };

  const [decks, setDecks] = useState(null);
  const [students, setStudents] = useState([]);
  const [mode, setMode] = useState('list'); // list | create | edit
  const [editId, setEditId] = useState(null);
  const [forbidden, setForbidden] = useState(false);
  const [isSchool, setIsSchool] = useState(false);

  // При зміні вкладки скидаємо стан редагування колод.
  useEffect(() => { setMode('list'); setEditId(null); }, [view]);
  useEffect(() => { getSchoolInfo().then((r) => setIsSchool(!!r.data.is_school)).catch(() => {}); }, []);

  const load = useCallback(async () => {
    try {
      const [d, s] = await Promise.all([getTeacherDecks(), getTeacherStudents()]);
      setDecks(d.data.decks || []);
      setStudents(s.data.students || []);
    } catch (e) {
      if (e?.response?.status === 403) setForbidden(true);
      else setDecks([]);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (forbidden) {
    return (
      <div className="page">
        <AppBar showProLink={false} />
        <div className="tch-wrap">
          <div className="tch-card"><p className="tch-muted">
            Цей розділ доступний лише викладачам.</p></div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <AppBar showProLink={false} />
      <div className="tch-wrap">
        <div className="tch-top">
          <h2 className="tch-title">Викладач</h2>
          <div className="tch-top-actions">
            {view === 'decks' && mode === 'list' && (
              <button className="tch-btn" onClick={() => setMode('create')}>+ Колода</button>
            )}
            <button className="tch-btn ghost sm" onClick={previewAsStudent}>👁 Як учень</button>
          </div>
        </div>

        <div className="tch-toggle-row">
          <button className={`tch-pill ${view === 'students' ? 'on' : ''}`}
                  onClick={() => setView('students')}>Учні</button>
          <button className={`tch-pill ${view === 'decks' ? 'on' : ''}`}
                  onClick={() => setView('decks')}>Колоди</button>
          <button className={`tch-pill ${view === 'calendar' ? 'on' : ''}`}
                  onClick={() => setView('calendar')}>Календар</button>
          <button className={`tch-pill ${view === 'stats' ? 'on' : ''}`}
                  onClick={() => setView('stats')}>Статистика</button>
          {isSchool && (
            <button className={`tch-pill ${view === 'school' ? 'on' : ''}`}
                    onClick={() => setView('school')}>Школа</button>
          )}
        </div>

        {view === 'students' && <StudentsList />}
        {view === 'calendar' && <CalendarManager />}
        {view === 'stats' && <TeacherStats students={students} />}
        {view === 'school' && <SchoolManager />}

        {view === 'decks' && mode === 'create' && (
          <CreateDeckForm
            students={students}
            onCreated={() => { setMode('list'); load(); }}
            onCancel={() => setMode('list')}
          />
        )}

        {view === 'decks' && mode === 'edit' && editId != null && (
          <EditDeck
            deckId={editId}
            students={students}
            onClose={() => { setEditId(null); setMode('list'); load(); }}
          />
        )}

        {view === 'decks' && mode === 'list' && (
          <>
            {decks === null && <p className="tch-muted">Завантаження…</p>}
            {decks && decks.length === 0 && (
              <div className="tch-card">
                <p className="tch-muted">Ще немає колод. Створіть першу — вставте
                  список «слово - переклад» і призначте учням.</p>
              </div>
            )}
            {decks && decks.map((d) => (
              <button
                key={d.id}
                className="tch-deck"
                onClick={() => { setEditId(d.id); setMode('edit'); }}
              >
                <div className="tch-deck-main">
                  <div className="tch-deck-title">{d.title}</div>
                  <div className="tch-deck-sub">
                    {d.word_count} слів · {d.assign_to_all
                      ? 'всім'
                      : `${d.assignment.count ?? 0} учням`}
                  </div>
                </div>
                <span className="tch-deck-edit">Редагувати ›</span>
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
