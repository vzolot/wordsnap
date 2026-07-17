import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AppBar from '../components/AppBar';
import CameraCapture from '../components/CameraCapture';
import { replayWelcome } from '../components/WelcomeStories';
import { useTenant } from '../contexts/TenantContext';
import { useRole } from '../contexts/RoleContext';
import {
  getTeacherDecks, getTeacherStudents, getTeacherDeck,
  createTeacherDeck, updateTeacherDeck, deleteTeacherDeck, getTeacherStudentDetail,
  getAvailability, putAvailability, getTeacherLessons, teacherCancelLesson,
  teacherCreateLesson,
  createDeckFromPhoto, assignHomework,
  getSchoolInfo, getSchoolInvites, getSchoolOverview, assignStudentToTeacher,
  getTeachers, addTeacher, setTeacherActive,
  getGroups, createGroup, setGroupMembers,
  getTeacherBilling, teacherBillingPay, setTeacherSeats,
} from '../api/client';

// Мова, яку вивчає учень → прапор + назва (для картки/списку учнів).
const LANG_META = {
  uk: { flag: '🇺🇦', name: 'Українська' },
  en: { flag: '🇬🇧', name: 'English' },
  fr: { flag: '🇫🇷', name: 'Français' },
  es: { flag: '🇪🇸', name: 'Español' },
  pl: { flag: '🇵🇱', name: 'Polski' },
  de: { flag: '🇩🇪', name: 'Deutsch' },
};
function langLabel(code) {
  const m = LANG_META[code];
  return m ? `${m.flag} ${m.name}` : (code ? code.toUpperCase() : null);
}

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

function shareInvite(url, text) {
  const tg = window.Telegram?.WebApp;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
  if (tg?.openTelegramLink) tg.openTelegramLink(shareUrl);
  else window.open(shareUrl, '_blank');
}

function ShareBotButton({ block }) {
  const { bot_username, is_school } = useTenant();
  const [inviteUrl, setInviteUrl] = useState(null);
  useEffect(() => {
    if (!is_school) return;
    getSchoolInvites().then((r) => setInviteUrl(r.data?.student_invite_url || null)).catch(() => {});
  }, [is_school]);
  // У школі — інвайт-посилання (учень кріпиться саме до цього викладача);
  // у соло — просто поділитися ботом.
  const useInvite = is_school && inviteUrl;
  const onClick = () => (useInvite
    ? shareInvite(inviteUrl, 'Приєднуйся — вчимо слова разом 📚')
    : shareBot(bot_username));
  return (
    <button
      className={`tch-btn${block ? '' : ' sm'}`}
      style={block ? { width: '100%', marginTop: 10 } : undefined}
      onClick={onClick}
    >
      🔗 {useInvite ? 'Запросити учнів' : 'Поділитися ботом'}
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
  const { role, ownerAsTeacher } = useRole();
  const { is_school } = useTenant();
  // Лише в адмін-режимі власник обирає викладача; у режимі викладача — свій календар.
  const isOwnerSchool = role === 'owner' && is_school && !ownerAsTeacher;
  // Власник школи керує календарем ОБРАНОГО викладача.
  const [teachers, setTeachers] = useState([]);
  const [teacherId, setTeacherId] = useState(null);

  useEffect(() => {
    if (!isOwnerSchool) return;
    getTeachers().then((r) => {
      const list = r.data.teachers || [];
      setTeachers(list);
      const first = list.find((t) => t.role === 'teacher') || list[0];
      if (first) setTeacherId(first.id);
    }).catch(() => {});
  }, [isOwnerSchool]);

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
    if (isOwnerSchool && !teacherId) return;  // власник ще не обрав викладача
    const [a, l, st] = await Promise.all([
      getAvailability(teacherId), getTeacherLessons(teacherId), getTeacherStudents(ownerAsTeacher),
    ]);
    const r = {};
    (a.data.availability || []).forEach((s) => {
      (r[s.weekday] = r[s.weekday] || []).push({ start: toHHMM(s.start_min), end: toHHMM(s.end_min) });
    });
    setRanges(r);
    setTz(a.data.timezone);
    setLessons(l.data.lessons || []);
    setStudents(st.data.students || []);
  }, [isOwnerSchool, teacherId]);
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
      await putAvailability(slots, teacherId);
      setMsg('Збережено ✅');
    } catch { setMsg('Не вдалося зберегти.'); }
    finally { setBusy(false); }
  };

  const cancelLesson = async (id) => {
    setBusy(true);
    try { await teacherCancelLesson(id, teacherId); await load(); } finally { setBusy(false); }
  };

  const book = async () => {
    if (!bkStudent || !bkDate || !bkTime) { setBkMsg('Оберіть учня, дату і час.'); return; }
    setBusy(true); setBkMsg('');
    try {
      // Дата+час у локальному поясі пристрою (= пояс викладача) → UTC ISO.
      const iso = new Date(`${bkDate}T${bkTime}:00`).toISOString();
      await teacherCreateLesson(Number(bkStudent), iso, null, teacherId);
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
      {/* Власник школи: обирає викладача, чий календар налаштовує. */}
      {isOwnerSchool && (
        <div className="tch-card">
          <h3 className="tch-h3">Календар викладача</h3>
          <select className="tch-input" value={teacherId || ''}
                  onChange={(e) => setTeacherId(Number(e.target.value) || null)}>
            <option value="">— оберіть викладача —</option>
            {teachers.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.role === 'owner' ? ' (ви)' : ''}</option>
            ))}
          </select>
        </div>
      )}

      {isOwnerSchool && !teacherId ? (
        <div className="tch-card"><p className="tch-muted">Оберіть викладача, щоб побачити й налаштувати його розклад.</p></div>
      ) : (
        <>
      {/* 1. Вільні години — інтервали, з яких учні самі бронюють. Дропдауни. */}
      <div className="tch-card">
        <h3 className="tch-h3">Вільні години</h3>
        <p className="tch-muted sm">
          Пояс: {(tz || '—').replace('Kiev', 'Kyiv')} · тривалість слота = тривалість уроку. Учні бачать ці інтервали для самостійного запису.
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
      )}
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
  const [camOpen, setCamOpen] = useState(false);
  const assignAll = target === 'all';

  useEffect(() => { getGroups().then((r) => setGroups(r.data.groups || [])).catch(() => {}); }, []);

  // Спільний пайплайн: base64-зображення → AI-розпізнавання пар → у текст.
  const recognize = async (b64, mime) => {
    setErr(''); setPhotoBusy(true);
    try {
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

  const onPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const { b64, mime } = await fileToB64(file);
    await recognize(b64, mime);
  };

  // Кадр із живої камери → закриваємо камеру → розпізнаємо.
  const onCameraCapture = async (b64, mime) => {
    setCamOpen(false);
    await recognize(b64, mime);
  };

  const toggle = (id) => setSelected((prev) => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const submit = async () => {
    setErr('');
    if (!title.trim()) { setErr('Вкажіть назву колоди'); return; }
    if (!text.trim()) { setErr('Додайте слова — по одному на рядок (переклад необовʼязковий)'); return; }
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
        ? 'Не розпізнав жодного слова. Додай по слову на рядок (переклад необовʼязковий).'
        : 'Не вдалося створити колоду. Спробуйте ще раз.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tch-card">
      <h3 className="tch-h3">Нова колода</h3>
      <p className="tch-muted sm" style={{ marginTop: 0 }}>
        Пиши слова <b>мовою, яку викладаєш</b> (напр. польською) — переклад рідною й приклади підставляться самі.
      </p>
      <input
        className="tch-input"
        placeholder="Назва колоди (напр. «Польська: побут»)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="tch-textarea"
        rows={8}
        placeholder={'Одне слово на рядок — переклад підставиться сам:\ndom\nwoda\n\nАбо задай свій переклад: «слово - переклад».\nМожна вставити CSV (2 колонки).'}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="tch-photo-row">
        <button type="button" className="tch-photo-btn"
                onClick={() => { setErr(''); setCamOpen(true); }} disabled={photoBusy}>
          📷 Зробити фото
        </button>
        <label className={`tch-photo-btn${photoBusy ? ' busy' : ''}`}>
          🖼 З файлу
          <input type="file" accept="image/*" onChange={onPhoto} disabled={photoBusy} hidden />
        </label>
      </div>
      {photoBusy && <p className="tch-muted sm">📷 Розпізнаю слова…</p>}
      {camOpen && (
        <CameraCapture onCapture={onCameraCapture} onClose={() => setCamOpen(false)} busy={photoBusy} />
      )}
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

  const delDeck = () => {
    const doDel = async () => {
      setBusy(true);
      try { await deleteTeacherDeck(deckId); onClose(); } finally { setBusy(false); }
    };
    const tg = window.Telegram?.WebApp;
    const q = 'Видалити колоду разом зі словами в учнів? Це не можна скасувати.';
    if (tg?.showConfirm) tg.showConfirm(q, (ok) => { if (ok) doDel(); });
    else if (window.confirm(q)) doDel();
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
        placeholder={'нове слово (переклад підставиться сам) або «слово - переклад»'}
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

      <div className="tch-actions" style={{ marginTop: 18 }}>
        <button className="tch-btn danger" onClick={delDeck} disabled={busy}>🗑 Видалити колоду</button>
      </div>
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
        <div style={{ minWidth: 0 }}>
          <h3 className="tch-h3">{d.display_name}</h3>
          {langLabel(d.target_lang) && (
            <div className="tch-muted sm">Вивчає: {langLabel(d.target_lang)}</div>
          )}
        </div>
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
  const { ownerAsTeacher } = useRole();
  const [students, setStudents] = useState(null);
  const [sel, setSel] = useState(null);

  useEffect(() => {
    getTeacherStudents(ownerAsTeacher).then((r) => setStudents(r.data.students || [])).catch(() => setStudents([]));
  }, [ownerAsTeacher]);

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
              {s.display_name}
              {langLabel(s.target_lang) && (
                <span className="tch-lang">{langLabel(s.target_lang)}</span>
              )}
              {s.at_risk && <span className="tch-risk">в ризику</span>}
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
  const [ov, setOv] = useState(null);
  const [teacherInvite, setTeacherInvite] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [o, inv] = await Promise.all([
      getSchoolOverview().then((r) => r.data).catch(() => null),
      getSchoolInvites().then((r) => r.data).catch(() => null),
    ]);
    setOv(o);
    setTeacherInvite(inv?.teacher_invite_url || null);
  }, []);
  useEffect(() => { load(); }, [load]);

  if (!ov) return <p className="tch-muted">Завантаження…</p>;
  const teachers = ov.teachers || [];
  const students = ov.students || [];

  const assign = async (studentId, teacherId) => {
    if (!teacherId) return;
    setBusy(true);
    try { await assignStudentToTeacher(studentId, Number(teacherId)); await load(); }
    finally { setBusy(false); }
  };

  return (
    <>
      {/* Викладачі: запросити + список зі своїм учнівським посиланням. */}
      <div className="tch-card">
        <h3 className="tch-h3">Викладачі</h3>
        {teacherInvite && (
          <>
            <p className="tch-muted sm" style={{ marginTop: 0 }}>
              Надішли посилання викладачу — він приєднається до школи одним тапом.
            </p>
            <button className="tch-btn" style={{ width: '100%', marginBottom: 10 }}
                    onClick={() => shareInvite(teacherInvite, 'Приєднуйся як викладач 👩‍🏫')}>
              🔗 Запросити викладача
            </button>
          </>
        )}
        {teachers.map((t) => (
          <div key={t.id} className="tch-word" style={{ flexWrap: 'wrap', gap: 6 }}>
            <span style={{ flex: 1, minWidth: 0 }}>
              {t.name}{t.role === 'owner' ? ' · власник' : ''} · {t.students} учн.
            </span>
            {t.invite_url && (
              <button className="tch-btn ghost sm"
                      onClick={() => shareInvite(t.invite_url, `Приєднуйся до викладача ${t.name} 📚`)}>
                🔗 Учні
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Призначення учнів викладачам. */}
      <div className="tch-card">
        <h3 className="tch-h3">Учні → викладач</h3>
        <p className="tch-muted sm" style={{ marginTop: 0 }}>
          Оберіть кожному учню викладача. Або просто поділись посиланням «🔗 Учні»
          потрібного викладача вище — тоді учень кріпиться до нього автоматично.
        </p>
        {students.length === 0 && <p className="tch-muted">Ще немає учнів. Запроси їх посиланням.</p>}
        {students.map((s) => (
          <div key={s.id} className="tch-word" style={{ gap: 8 }}>
            <span style={{ flex: 1, minWidth: 0 }}>{s.name}</span>
            <select className="tch-input" style={{ maxWidth: 170 }} value={s.teacher_id || ''}
                    onChange={(e) => assign(s.id, e.target.value)} disabled={busy}>
              <option value="">— викладач —</option>
              {teachers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
        ))}
      </div>
    </>
  );
}

// Статистика власника школи — по кожному викладачу.
function SchoolStats() {
  const [data, setData] = useState(null);
  useEffect(() => { getSchoolOverview().then((r) => setData(r.data)).catch(() => setData(null)); }, []);
  if (!data) return <p className="tch-muted">Завантаження…</p>;
  const teachers = data.teachers || [];
  if (teachers.length === 0) return (
    <>
      <div className="tch-card"><p className="tch-muted">Ще немає викладачів.</p></div>
      <TeacherBilling />
    </>
  );
  return (
    <>
      {teachers.map((t) => (
        <div key={t.id} className="tch-card">
          <div className="tch-billing-title">{t.name}{t.role === 'owner' ? ' (ви)' : ''}</div>
          <div className="tch-kpis" style={{ marginTop: 8 }}>
            <Kpi value={t.students} label="учнів" />
            <Kpi value={t.lessons_done_month} label="занять/міс" />
            <Kpi value={t.lessons_done_total} label="усього" />
            <Kpi value={t.lessons_scheduled} label="заплановано" />
          </div>
        </div>
      ))}
      <TeacherBilling />
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

// Оплата сервісу власником. У школі — селектор кількості викладацьких місць
// (передоплата): база $19 покриває власника, кожне місце +$5.
function TeacherBilling() {
  const [b, setB] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getTeacherBilling().then((r) => setB(r.data)).catch(() => setB(null)); }, []);

  const pay = async () => {
    setBusy(true);
    try {
      const r = await teacherBillingPay();
      const url = r.data?.payment_url;
      if (url) {
        const tg = window.Telegram?.WebApp;
        if (tg?.openLink) tg.openLink(url); else window.open(url, '_blank');
      }
    } finally { setBusy(false); }
  };

  // Змінити кількість оплачених місць (не менше за фактичних викладачів).
  const changeSeats = async (delta) => {
    if (!b) return;
    const next = Math.max(b.teachers || 0, Math.min(50, (b.seats || 0) + delta));
    if (next === b.seats) return;
    setBusy(true);
    try {
      const r = await setTeacherSeats(next);
      setB(r.data);
    } finally { setBusy(false); }
  };

  if (!b) return null;
  const fmt = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
  };
  const active = b.active;
  const statusLine = active
    ? `${b.auto_renew ? 'Автопродовження' : 'Активна'} · до ${fmt(b.expires_at)}${typeof b.days_left === 'number' ? ` (${b.days_left} дн.)` : ''}`
    : b.status === 'past_due' ? 'Прострочено — сервіс може призупинитись'
    : b.status === 'trial' ? 'Пробний період' : 'Неактивна';
  const statusCls = active ? '' : b.status === 'past_due' ? 'bad' : 'muted';
  const seats = b.seats || 0;
  const breakdown = b.is_school
    ? (seats > 0
        ? `$${b.base_usd} база (ви) + $${b.per_extra_usd} × ${seats} = $${b.price_usd}`
        : `$${b.base_usd} база — ви як викладач`)
    : null;

  return (
    <div className="tch-card tch-billing">
      <div className="tch-billing-row">
        <div style={{ minWidth: 0 }}>
          <div className="tch-billing-title">💳 Підписка · ${b.price_usd}/міс</div>
          <div className={`tch-billing-status ${statusCls}`}>{statusLine}</div>
        </div>
        <button className="tch-btn sm" onClick={pay} disabled={busy}>
          {active ? 'Продовжити' : `Оплатити $${b.price_usd}`}
        </button>
      </div>

      {b.is_school && (
        <div className="tch-seats">
          <div className="tch-seats-label">
            Викладачів (окрім вас) · ${b.per_extra_usd}/міс кожен
            {b.teachers > 0 && <span className="tch-muted sm"> · зараз у школі: {b.teachers}</span>}
          </div>
          <div className="tch-seats-ctl">
            <button className="tch-seats-btn" onClick={() => changeSeats(-1)}
              disabled={busy || seats <= (b.teachers || 0)} aria-label="Менше">−</button>
            <span className="tch-seats-n">{seats}</span>
            <button className="tch-seats-btn" onClick={() => changeSeats(1)}
              disabled={busy || seats >= 50} aria-label="Більше">+</button>
          </div>
        </div>
      )}

      {breakdown && <div className="tch-billing-status muted" style={{ marginTop: 6 }}>{breakdown}</div>}
    </div>
  );
}

// Викладацька статистика: зведені KPI + детальний прогрес по ОБРАНИХ учнях
// (перевикористовує StudentPicker для вибору і StudentDetail для показу).
function TeacherStats({ students }) {
  const { role, ownerAsTeacher } = useRole();
  // Оплату сервісу бачить лише власник (адмін) — не звичайний викладач і не
  // власник у режимі викладача. За доданих викладачів платить адміністратор.
  const showBilling = role === 'owner' && !ownerAsTeacher;
  const [sel, setSel] = useState(new Set());
  const toggle = (id) => setSel((prev) => {
    const n = new Set(prev);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });

  if (!students || students.length === 0) {
    return (
      <>
        <div className="tch-card">
          <p className="tch-muted">Статистика по учнях зʼявиться, коли вони приєднаються.</p>
        </div>
        {showBilling && <TeacherBilling />}
      </>
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

      {showBilling && <TeacherBilling />}
    </>
  );
}

export default function TeacherPage() {
  // Активна вкладка — з URL (?tab=), щоб нижня викладацька навігація й
  // внутрішні пігулки були одним джерелом істини.
  const [sp, setSp] = useSearchParams();
  const { setStudentPreview, role, ownerAsTeacher, setOwnerAsTeacher, isTeacher, roleLoaded } = useRole();
  const { is_school } = useTenant();
  const isOwner = is_school && role === 'owner';
  // Адмін-вигляд (керування школою) активний, лише коли власник НЕ в режимі викладача.
  const isOwnerSchool = isOwner && !ownerAsTeacher;
  const view = sp.get('tab') || (isOwnerSchool ? 'school' : 'students');
  const setView = (v) => setSp({ tab: v }, { replace: true });

  const navigate = useNavigate();
  // Підтверджений НЕ-викладач на /teacher (напр. учень WordSnap, якого сюди
  // завела чужа роль зі спільного кешу) → назад на головну, без «forbidden».
  useEffect(() => {
    if (roleLoaded && !isTeacher) navigate('/', { replace: true });
  }, [roleLoaded, isTeacher, navigate]);
  const previewAsStudent = () => { setStudentPreview(true); navigate('/'); };
  // Власник ⇄ викладач: у режимі викладача власник керує лише своїми учнями.
  const toggleOwnerMode = () => {
    const next = !ownerAsTeacher;
    setOwnerAsTeacher(next);
    setSp({ tab: next ? 'students' : 'school' }, { replace: true });
  };

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
      const [d, s] = await Promise.all([
        getTeacherDecks(ownerAsTeacher), getTeacherStudents(ownerAsTeacher),
      ]);
      setDecks(d.data.decks || []);
      setStudents(s.data.students || []);
    } catch (e) {
      if (e?.response?.status === 403) setForbidden(true);
      else setDecks([]);
    }
  }, [ownerAsTeacher]);
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
            {isOwner ? (
              <button className="tch-btn ghost sm" onClick={toggleOwnerMode}>
                {ownerAsTeacher ? '🛠 Адміністратор' : '👩‍🏫 Як викладач'}
              </button>
            ) : (
              <button className="tch-btn ghost sm" onClick={previewAsStudent}>👁 Як учень</button>
            )}
          </div>
        </div>

        {view === 'students' && <StudentsList />}
        {view === 'calendar' && <CalendarManager />}
        {view === 'stats' && (isOwnerSchool ? <SchoolStats /> : <TeacherStats students={students} />)}
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

        {mode === 'list' && (
          <button
            className="link-back"
            style={{ marginTop: 22, color: 'var(--text-2)', display: 'block' }}
            onClick={replayWelcome}
          >
            Переглянути онбординг
          </button>
        )}
      </div>
    </div>
  );
}
