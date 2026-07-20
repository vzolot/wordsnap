import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AppBar from '../components/AppBar';
import CameraCapture from '../components/CameraCapture';
import { replayWelcome } from '../components/WelcomeStories';
import { useTenant } from '../contexts/TenantContext';
import { useT } from '../contexts/LangContext';
import { useRole } from '../contexts/RoleContext';
import {
  getTeacherDecks, getTeacherStudents, getTeacherDeck,
  createTeacherDeck, updateTeacherDeck, deleteTeacherDeck, getTeacherStudentDetail, deleteTeacherStudent,
  getAvailability, putAvailability, getTeacherLessons, teacherCancelLesson,
  teacherCreateLesson,
  createDeckFromPhoto, createDeckFromVoice, assignHomework,
  getSchoolInfo, getSchoolInvites, getSchoolOverview, assignStudentToTeacher,
  getTeachers, addTeacher, setTeacherActive, deleteTeacher,
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
function shareBot(username, text) {
  const url = botLink(username);
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
  const { t } = useT();
  const { bot_username, is_school } = useTenant();
  const [inviteUrl, setInviteUrl] = useState(null);
  useEffect(() => {
    if (!is_school) return;
    getSchoolInvites().then((r) => setInviteUrl(r.data?.student_invite_url || null)).catch(() => {});
  }, [is_school]);
  // У школі – інвайт-посилання (учень кріпиться саме до цього викладача);
  // у соло – просто поділитися ботом.
  const useInvite = is_school && inviteUrl;
  const onClick = () => (useInvite
    ? shareInvite(inviteUrl, t('teacher.share_text'))
    : shareBot(bot_username, t('teacher.share_text')));
  return (
    <button
      className={`tch-btn${block ? '' : ' sm'}`}
      style={block ? { width: '100%', marginTop: 10 } : undefined}
      onClick={onClick}
    >
      🔗 {useInvite ? t('teacher.invite_students') : t('teacher.share_app')}
    </button>
  );
}

// Рейтинг усіх учнів тенанта за сумарним XP (замість тижневого топу повторень).
function StudentRanking({ students }) {
  const { t } = useT();
  if (!students || students.length === 0) return null;
  const ranked = [...students].sort((a, b) => (b.total_xp || 0) - (a.total_xp || 0));
  const medals = ['🥇', '🥈', '🥉'];
  return (
    <div className="tch-card">
      <h3 className="tch-h3">🏆 {t('teacher.ranking')}</h3>
      {ranked.map((s, i) => (
        <div key={s.id} className="tch-word">
          <span>{medals[i] || `${i + 1}.`} <b>{s.display_name}</b></span>
          <span className="tch-muted">{t('teacher.xp_n', { n: s.total_xp || 0 })}</span>
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

// Blob (аудіозапис) → чистий base64 (без data-URL префіксу).
function blobToB64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => { const s = String(r.result); resolve(s.slice(s.indexOf(',') + 1)); };
    r.onerror = reject;
    r.readAsDataURL(blob);
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
const dayLabel = (d, t) => `${t(`teacher.dow${d.getDay()}`)}, ${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
const hhmmLocal = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;

function CalendarManager() {
  const { t } = useT();
  const { role, ownerAsTeacher } = useRole();
  const { is_school } = useTenant();
  // Лише в адмін-режимі власник обирає викладача; у режимі викладача – свій календар.
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
      setMsg(t('teacher.saved'));
    } catch { setMsg(t('teacher.save_failed')); }
    finally { setBusy(false); }
  };

  const cancelLesson = async (id) => {
    setBusy(true);
    try { await teacherCancelLesson(id, teacherId); await load(); } finally { setBusy(false); }
  };

  const book = async () => {
    if (!bkStudent || !bkDate || !bkTime) { setBkMsg(t('teacher.pick_student_date_time')); return; }
    setBusy(true); setBkMsg('');
    try {
      // Дата+час у локальному поясі пристрою (= пояс викладача) → UTC ISO.
      const iso = new Date(`${bkDate}T${bkTime}:00`).toISOString();
      await teacherCreateLesson(Number(bkStudent), iso, null, teacherId);
      setBkMsg(t('teacher.lesson_added'));
      setBkDate('');
      await load();
    } catch (e) {
      const err = e?.response?.data?.detail;
      setBkMsg(err === 'slot_taken' ? t('teacher.slot_taken') : t('teacher.lesson_add_failed'));
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
      if (!_map.has(key)) { const g = { label: dayLabel(d, t), items: [] }; _map.set(key, g); byDay.push(g); }
      _map.get(key).items.push(l);
    });

  return (
    <>
      {/* Власник школи: обирає викладача, чий календар налаштовує. */}
      {isOwnerSchool && (
        <div className="tch-card">
          <h3 className="tch-h3">{t('teacher.teacher_calendar')}</h3>
          <select className="tch-input" value={teacherId || ''}
                  onChange={(e) => setTeacherId(Number(e.target.value) || null)}>
            <option value="">{t('teacher.pick_teacher_opt')}</option>
            {teachers.map((tt) => (
              <option key={tt.id} value={tt.id}>{tt.name}{tt.role === 'owner' ? t('teacher.you_suffix') : ''}</option>
            ))}
          </select>
        </div>
      )}

      {isOwnerSchool && !teacherId ? (
        <div className="tch-card"><p className="tch-muted">{t('teacher.pick_teacher_hint')}</p></div>
      ) : (
        <>
      {/* 1. Вільні години – інтервали, з яких учні самі бронюють. Дропдауни. */}
      <div className="tch-card">
        <h3 className="tch-h3">{t('teacher.free_hours')}</h3>
        <p className="tch-muted sm">
          {t('teacher.free_hours_hint', { tz: (tz || '–').replace('Kiev', 'Kyiv') })}
        </p>
        {WEEKDAYS.map((name, wd) => (
          <div key={wd} className="tch-wdrow">
            <div className="tch-wd">{t(`teacher.dow${(wd + 1) % 7}`)}</div>
            <div className="tch-wdranges">
              {(ranges[wd] || []).map((r, i) => (
                <div key={i} className="tch-range">
                  <TimeSelect value={r.start} onChange={(v) => setField(wd, i, 'start', v)} />
                  <span>–</span>
                  <TimeSelect value={r.end} onChange={(v) => setField(wd, i, 'end', v)} />
                  <button className="tch-x" onClick={() => rmRange(wd, i)}>✕</button>
                </div>
              ))}
              <button className="tch-addrange" onClick={() => addRange(wd)}>{t('teacher.add_interval')}</button>
            </div>
          </div>
        ))}
        {msg && <p className="tch-ok">{msg}</p>}
        <div className="tch-actions">
          <button className="tch-btn" onClick={save} disabled={busy}>{t('teacher.save_free_hours')}</button>
        </div>
      </div>

      {/* 2. Ручне бронювання уроку викладачем (окремо від вільних годин). */}
      <div className="tch-card">
        <h3 className="tch-h3">{t('teacher.book_manually')}</h3>
        {students.length === 0 ? (
          <p className="tch-muted sm">{t('teacher.add_students_first')}</p>
        ) : (
          <>
            <div className="tch-book">
              <select className="tch-time grow" value={bkStudent} onChange={(e) => setBkStudent(e.target.value)}>
                <option value="">{t('teacher.student_opt')}</option>
                {students.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
              </select>
              <input type="date" className="tch-time" value={bkDate} onChange={(e) => setBkDate(e.target.value)} />
              <TimeSelect value={bkTime} onChange={setBkTime} />
            </div>
            {bkMsg && <p className="tch-ok">{bkMsg}</p>}
            <div className="tch-actions">
              <button className="tch-btn" onClick={book} disabled={busy}>{t('teacher.book')}</button>
            </div>
          </>
        )}
      </div>

      {/* 3. Денний розклад: хто і о котрій. */}
      <div className="tch-card">
        <h3 className="tch-h3">{t('teacher.schedule')}</h3>
        {byDay.length === 0 && <p className="tch-muted">{t('teacher.no_bookings')}</p>}
        {byDay.map((day) => (
          <div key={day.label} className="tch-day">
            <div className="tch-day-h">{day.label}</div>
            {day.items.map((l) => (
              <div key={l.id} className="tch-word">
                <span>🕑 <b>{hhmmLocal(new Date(l.starts_at_utc))}</b> – {l.student_name || t('teacher.student_word')}</span>
                <button className="tch-btn ghost sm" onClick={() => cancelLesson(l.id)} disabled={busy}>{t('teacher.cancel_lesson')}</button>
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

function relTime(iso, t) {
  if (!iso) return t('teacher.never_visited');
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return t('teacher.today');
  if (days === 1) return t('teacher.yesterday');
  if (days < 7) return t('teacher.days_ago', { n: days });
  if (days < 30) return t('teacher.weeks_ago', { n: Math.floor(days / 7) });
  return t('teacher.months_ago', { n: Math.floor(days / 30) });
}

// Режим викладача (white-label M5). Текст українською – аудиторія викладачів
// україномовна діаспора (узгоджено з ТЗ; повний i18n – за потреби пізніше).

function StudentPicker({ students, selected, onToggle }) {
  const { t } = useT();
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
        <p className="tch-muted">{t('teacher.no_students_share')}</p>
      )}
    </div>
  );
}

function CreateDeckForm({ students, onCreated, onCancel }) {
  const { t } = useT();
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
  const [recording, setRecording] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const mrRef = useRef(null);
  const chunksRef = useRef([]);
  const assignAll = target === 'all';

  useEffect(() => { getGroups().then((r) => setGroups(r.data.groups || [])).catch(() => {}); }, []);

  const appendPairs = (pairs) => {
    const lines = pairs.map((p) => `${p.word} - ${p.translation}`).join('\n');
    setText((prev) => (prev.trim() ? prev.trim() + '\n' : '') + lines);
  };

  // Спільний пайплайн: base64-зображення → AI-розпізнавання пар → у текст.
  const recognize = async (b64, mime) => {
    setErr(''); setPhotoBusy(true);
    try {
      const r = await createDeckFromPhoto(b64, mime);
      const pairs = r.data.pairs || [];
      if (pairs.length === 0) { setErr(t('teacher.photo_no_words')); return; }
      appendPairs(pairs);
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(d === 'ai_snap_limit_reached'
        ? t('teacher.ai_limit_photo')
        : t('teacher.photo_failed'));
    } finally { setPhotoBusy(false); }
  };

  // Голос: диктуємо слова → Whisper-транскрипт → пари → у текст.
  const recognizeVoice = async (b64, mime) => {
    setErr(''); setVoiceBusy(true);
    try {
      const r = await createDeckFromVoice(b64, mime);
      const pairs = r.data.pairs || [];
      if (pairs.length === 0) { setErr(t('teacher.voice_no_words')); return; }
      appendPairs(pairs);
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(d === 'ai_snap_limit_reached'
        ? t('teacher.ai_limit_voice')
        : t('teacher.voice_failed'));
    } finally { setVoiceBusy(false); }
  };

  const startVoice = async () => {
    setErr('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'];
      const mimeType = types.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || '';
      const mr = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop());
        setRecording(false);
        const type = mr.mimeType || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        const b64 = await blobToB64(blob);
        await recognizeVoice(b64, type.split(';')[0]);
      };
      mrRef.current = mr;
      mr.start();
      setRecording(true);
    } catch {
      setErr(t('teacher.mic_denied'));
    }
  };
  const stopVoice = () => { try { mrRef.current?.stop(); } catch { /* noop */ } };

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
    if (!title.trim()) { setErr(t('teacher.enter_deck_title')); return; }
    if (!text.trim()) { setErr(t('teacher.add_words_line')); return; }
    if (target === 'group' && !groupId) { setErr(t('teacher.pick_group')); return; }
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
        ? t('teacher.no_pairs')
        : t('teacher.deck_create_failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tch-card">
      <h3 className="tch-h3">{t('teacher.new_deck')}</h3>
      <p className="tch-muted sm" style={{ marginTop: 0 }}>
        {t('teacher.new_deck_hint')}
      </p>
      <input
        className="tch-input"
        placeholder={t('teacher.deck_title_ph')}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="tch-textarea"
        rows={8}
        placeholder={t('teacher.deck_words_ph')}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="tch-photo-row">
        <button type="button" className="tch-photo-btn"
                onClick={() => { setErr(''); setCamOpen(true); }} disabled={photoBusy}>
          {t('teacher.take_photo')}
        </button>
        <label className={`tch-photo-btn${photoBusy ? ' busy' : ''}`}>
          {t('teacher.from_file')}
          <input type="file" accept="image/*" onChange={onPhoto} disabled={photoBusy} hidden />
        </label>
        <button type="button" className={`tch-photo-btn${recording ? ' rec' : ''}`}
                onClick={recording ? stopVoice : startVoice} disabled={voiceBusy}>
          {recording ? t('teacher.stop') : t('teacher.dictate')}
        </button>
      </div>
      {photoBusy && <p className="tch-muted sm">{t('teacher.recognizing_photo')}</p>}
      {recording && <p className="tch-muted sm">{t('teacher.recording_hint')}</p>}
      {voiceBusy && <p className="tch-muted sm">{t('teacher.recognizing_voice')}</p>}
      {camOpen && (
        <CameraCapture onCapture={onCameraCapture} onClose={() => setCamOpen(false)} busy={photoBusy} />
      )}
      <div className="tch-toggle-row">
        <button className={`tch-pill ${target === 'all' ? 'on' : ''}`}
                onClick={() => setTarget('all')}>{t('teacher.assign_all')}</button>
        <button className={`tch-pill ${target === 'selected' ? 'on' : ''}`}
                onClick={() => setTarget('selected')}>{t('teacher.assign_selected')}</button>
        {groups.length > 0 && (
          <button className={`tch-pill ${target === 'group' ? 'on' : ''}`}
                  onClick={() => setTarget('group')}>{t('teacher.assign_group')}</button>
        )}
      </div>
      {target === 'selected' && (
        <StudentPicker students={students} selected={selected} onToggle={toggle} />
      )}
      {target === 'group' && (
        <select className="tch-input" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">{t('teacher.pick_group_opt')}</option>
          {groups.map((g) => <option key={g.id} value={g.id}>{g.name} ({g.members})</option>)}
        </select>
      )}
      {err && <p className="tch-err">{err}</p>}
      <div className="tch-actions">
        <button className="tch-btn ghost" onClick={onCancel} disabled={busy}>{t('teacher.cancel')}</button>
        <button className="tch-btn" onClick={submit} disabled={busy}>
          {busy ? t('teacher.creating') : t('teacher.create_deck')}
        </button>
      </div>
    </div>
  );
}

function EditDeck({ deckId, students, onClose }) {
  const { t } = useT();
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
      setMsg(t('teacher.words_added', { n: r.data.added_words ?? 0 }));
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
    const q = t('teacher.confirm_delete_deck');
    if (tg?.showConfirm) tg.showConfirm(q, (ok) => { if (ok) doDel(); });
    else if (window.confirm(q)) doDel();
  };

  if (!deck) return <div className="tch-card"><p className="tch-muted">{t('teacher.loading')}</p></div>;

  return (
    <div className="tch-card">
      <div className="tch-edit-head">
        <h3 className="tch-h3">{deck.title}</h3>
        <button className="tch-btn ghost sm" onClick={onClose}>{t('teacher.back')}</button>
      </div>
      <p className="tch-muted">
        {deck.assign_to_all ? t('teacher.assigned_all') : t('teacher.assigned_selected', { n: deck.assignee_user_ids.length })}
        {' · '}{t('teacher.words_count', { n: deck.words.length })}
      </p>

      <div className="tch-wordlist">
        {deck.words.map((w) => (
          <div key={w.id} className="tch-word">
            <span><b>{w.word}</b> – {w.translation}</span>
            <button className="tch-x" onClick={() => removeWord(w.id)} disabled={busy} aria-label={t('teacher.delete')}>✕</button>
          </div>
        ))}
      </div>

      <h4 className="tch-h4">{t('teacher.add_words')}</h4>
      <textarea
        className="tch-textarea"
        rows={4}
        placeholder={t('teacher.add_words_ph')}
        value={addText}
        onChange={(e) => setAddText(e.target.value)}
      />
      {msg && <p className="tch-ok">{msg}</p>}
      <div className="tch-actions">
        <button className="tch-btn" onClick={addWords} disabled={busy}>
          {busy ? t('teacher.saving') : t('teacher.add')}
        </button>
      </div>
      <p className="tch-muted sm">{t('teacher.new_words_hint')}</p>

      <h4 className="tch-h4">{t('teacher.homework_deadline')}</h4>
      <DeadlineAssign deckId={deckId} />

      <div className="tch-actions" style={{ marginTop: 18 }}>
        <button className="tch-btn danger" onClick={delDeck} disabled={busy}>{t('teacher.delete_deck')}</button>
      </div>
    </div>
  );
}

function DeadlineAssign({ deckId }) {
  const { t } = useT();
  const [due, setDue] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const assign = async () => {
    if (!due) { setMsg(t('teacher.pick_deadline')); return; }
    setBusy(true); setMsg('');
    try {
      const iso = new Date(due).toISOString();
      const r = await assignHomework(deckId, iso);
      setMsg(t('teacher.deadline_assigned', { n: r.data.assigned }));
    } catch { setMsg(t('teacher.assign_failed')); }
    finally { setBusy(false); }
  };
  return (
    <div className="tch-range" style={{ flexWrap: 'wrap' }}>
      <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      <button className="tch-btn sm" onClick={assign} disabled={busy}>{t('teacher.assign_all_btn')}</button>
      {msg && <p className="tch-ok" style={{ width: '100%' }}>{msg}</p>}
    </div>
  );
}

function StudentDetail({ studentId, onClose, onDeleted }) {
  const { t } = useT();
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    getTeacherStudentDetail(studentId).then((r) => setD(r.data)).catch(() => setErr(true));
  }, [studentId]);

  const removeStudent = async () => {
    if (!window.confirm(t('teacher.confirm_delete_student'))) return;
    setBusy(true);
    try { await deleteTeacherStudent(studentId); (onDeleted || onClose)?.(); }
    catch { setBusy(false); }
  };

  if (err) return <div className="tch-card"><p className="tch-muted">{t('teacher.load_failed')}</p></div>;
  if (!d) return <div className="tch-card"><p className="tch-muted">{t('teacher.loading')}</p></div>;

  const STR = { strong: t('teacher.strong'), learning: t('teacher.learning'), weak: t('teacher.weak') };

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
            <div className="tch-muted sm">{t('teacher.learns', { lang: langLabel(d.target_lang) })}</div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <button className="tch-btn ghost sm" onClick={removeStudent} disabled={busy}>🗑 {t('teacher.delete')}</button>
          <button className="tch-btn ghost sm" onClick={onClose}>{t('teacher.back')}</button>
        </div>
      </div>
      <div className="tch-metrics">
        <div className="tch-metric"><b>{d.streak}</b><span>{t('teacher.days_streak')}</span></div>
        <div className="tch-metric"><b>{d.reviews_7d}</b><span>{t('teacher.last_7d')}</span></div>
        <div className="tch-metric"><b>{d.reviews_30d}</b><span>{t('teacher.last_30d')}</span></div>
      </div>

      <h4 className="tch-h4">{t('teacher.activity_30d')}</h4>
      <div className="tch-spark">
        {bars.map((b) => (
          <div key={b.key} className="tch-spark-bar"
               style={{ height: `${Math.max(3, Math.round(100 * b.n / maxN))}%` }}
               title={`${b.key}: ${b.n}`} />
        ))}
      </div>

      <h4 className="tch-h4">{t('teacher.deck_progress')}</h4>
      {d.decks.length === 0 && <p className="tch-muted">{t('teacher.no_assigned_decks')}</p>}
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

      <h4 className="tch-h4">{t('teacher.words_phrases')}</h4>
      {(!d.words || d.words.length === 0) && <p className="tch-muted">{t('teacher.no_words_student')}</p>}
      {(d.words || []).map((w) => (
        <div key={w.word_id} className="tch-word">
          <span style={{ minWidth: 0 }}><b>{w.word}</b> – {w.translation}</span>
          <span className={`tch-strength ${w.strength}`}>
            {STR[w.strength] || t('teacher.learning')}{w.strength === 'weak' && w.error_rate > 0 ? ` · ${Math.round(w.error_rate * 100)}%` : ''}
          </span>
        </div>
      ))}
    </div>
  );
}

function StudentsList() {
  const { t } = useT();
  const { ownerAsTeacher } = useRole();
  const [students, setStudents] = useState(null);
  const [sel, setSel] = useState(null);

  const load = useCallback(() => {
    getTeacherStudents(ownerAsTeacher).then((r) => setStudents(r.data.students || [])).catch(() => setStudents([]));
  }, [ownerAsTeacher]);
  useEffect(() => { load(); }, [load]);

  if (sel != null) return <StudentDetail studentId={sel} onClose={() => setSel(null)} onDeleted={() => { setSel(null); load(); }} />;
  if (students === null) return <p className="tch-muted">{t('teacher.loading')}</p>;
  if (students.length === 0) return (
    <div className="tch-card">
      <p className="tch-muted">{t('teacher.no_students_share')}</p>
      <ShareBotButton block />
    </div>
  );

  return (
    <>
      <StudentRanking students={students} />
      <div className="tch-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="tch-muted sm">{t('teacher.students_n', { n: students.length })}</span>
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
              {s.at_risk && <span className="tch-risk">{t('teacher.at_risk')}</span>}
            </div>
            <div className="tch-deck-sub">
              ⭐ {s.total_xp || 0} XP · 🔥 {s.streak} · {t('teacher.learned_pct', { n: s.learned_pct })} · {relTime(s.last_visit, t)}
            </div>
          </div>
          <span className="tch-deck-edit">›</span>
        </button>
      ))}
    </>
  );
}

function GroupEditor({ group, students, onDone }) {
  const { t } = useT();
  const [sel, setSel] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const toggle = (id) => setSel((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const save = async () => {
    setBusy(true);
    try { await setGroupMembers(group.id, [...sel]); onDone(); } finally { setBusy(false); }
  };
  return (
    <div className="tch-card">
      <h4 className="tch-h4">{t('teacher.group_members', { name: group.name })}</h4>
      <StudentPicker students={students} selected={sel} onToggle={toggle} />
      <div className="tch-actions">
        <button className="tch-btn ghost sm" onClick={onDone}>{t('teacher.back_plain')}</button>
        <button className="tch-btn sm" onClick={save} disabled={busy}>{t('teacher.save_members')}</button>
      </div>
    </div>
  );
}

function SchoolManager() {
  const { t } = useT();
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

  if (!ov) return <p className="tch-muted">{t('teacher.loading')}</p>;
  const teachers = ov.teachers || [];
  const students = ov.students || [];

  const assign = async (studentId, teacherId) => {
    if (!teacherId) return;
    setBusy(true);
    try { await assignStudentToTeacher(studentId, Number(teacherId)); await load(); }
    finally { setBusy(false); }
  };

  const removeTeacher = async (id, name) => {
    if (!window.confirm(t('teacher.confirm_delete_teacher', { name }))) return;
    setBusy(true);
    try { await deleteTeacher(id); await load(); } finally { setBusy(false); }
  };

  return (
    <>
      {/* Викладачі: запросити + список зі своїм учнівським посиланням. */}
      <div className="tch-card">
        <h3 className="tch-h3">{t('teacher.teachers')}</h3>
        {teacherInvite && (
          <>
            <p className="tch-muted sm" style={{ marginTop: 0 }}>
              {t('teacher.invite_teacher_hint')}
            </p>
            <button className="tch-btn" style={{ width: '100%', marginBottom: 10 }}
                    onClick={() => shareInvite(teacherInvite, t('teacher.invite_teacher_msg'))}>
              {t('teacher.invite_teacher')}
            </button>
          </>
        )}
        {teachers.map((tt) => (
          <div key={tt.id} className="tch-word" style={{ flexWrap: 'wrap', gap: 6 }}>
            <span style={{ flex: 1, minWidth: 0 }}>
              {tt.name}{tt.role === 'owner' ? t('teacher.owner_suffix') : ''} · {t('teacher.students_short_n', { n: tt.students })}
              {langLabel(tt.target_lang) && <span className="tch-lang">{t('teacher.teaches', { lang: langLabel(tt.target_lang) })}</span>}
            </span>
            {tt.invite_url && (
              <button className="tch-btn ghost sm"
                      onClick={() => shareInvite(tt.invite_url, t('teacher.invite_student_msg', { name: tt.name }))}>
                {t('teacher.invite_students_link')}
              </button>
            )}
            {tt.role !== 'owner' && (
              <button className="tch-btn ghost sm" title={t('teacher.delete_teacher_title')}
                      onClick={() => removeTeacher(tt.id, tt.name)} disabled={busy}>🗑</button>
            )}
          </div>
        ))}
      </div>

      {/* Призначення учнів викладачам. */}
      <div className="tch-card">
        <h3 className="tch-h3">{t('teacher.students_to_teacher')}</h3>
        <p className="tch-muted sm" style={{ marginTop: 0 }}>
          {t('teacher.assign_hint')}
        </p>
        {students.length === 0 && <p className="tch-muted">{t('teacher.no_students_invite')}</p>}
        {students.map((s) => (
          <div key={s.id} className="tch-word" style={{ gap: 8 }}>
            <span style={{ flex: 1, minWidth: 0 }}>{s.name}{langLabel(s.target_lang) && <span className="tch-lang">{langLabel(s.target_lang)}</span>}</span>
            <select className="tch-input" style={{ maxWidth: 170 }} value={s.teacher_id || ''}
                    onChange={(e) => assign(s.id, e.target.value)} disabled={busy}>
              <option value="">{t('teacher.teacher_opt')}</option>
              {teachers.map((tt) => <option key={tt.id} value={tt.id}>{tt.name}</option>)}
            </select>
          </div>
        ))}
      </div>
    </>
  );
}

// Статистика власника школи – по кожному викладачу.
function SchoolStats() {
  const { t } = useT();
  const [data, setData] = useState(null);
  useEffect(() => { getSchoolOverview().then((r) => setData(r.data)).catch(() => setData(null)); }, []);
  if (!data) return <p className="tch-muted">{t('teacher.loading')}</p>;
  const teachers = data.teachers || [];
  if (teachers.length === 0) return (
    <>
      <div className="tch-card"><p className="tch-muted">{t('teacher.no_teachers')}</p></div>
      <TeacherBilling />
    </>
  );
  return (
    <>
      <p className="tch-muted sm" style={{ margin: '0 0 6px' }}>
        {t('teacher.lessons_legend')}
      </p>
      {teachers.map((tt) => (
        <div key={tt.id} className="tch-card">
          <div className="tch-billing-title">
            {tt.name}{tt.role === 'owner' ? t('teacher.you_suffix') : ''}
            {langLabel(tt.target_lang) && <span className="tch-lang">{t('teacher.teaches', { lang: langLabel(tt.target_lang) })}</span>}
          </div>
          <div className="tch-kpis" style={{ marginTop: 8 }}>
            <Kpi value={tt.students} label={t('teacher.kpi_students')} />
            <Kpi value={tt.lessons_done_month} label={t('teacher.kpi_lessons_month')} />
            <Kpi value={tt.lessons_done_total} label={t('teacher.kpi_done_total')} />
            <Kpi value={tt.lessons_scheduled} label={t('teacher.kpi_scheduled')} />
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

// Оплата сервісу власником. У школі – селектор кількості викладацьких місць
// (передоплата): база $19 покриває власника, кожне місце +$5.
function TeacherBilling() {
  const { t } = useT();
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
    ? `${b.auto_renew ? t('teacher.auto_renew') : t('teacher.active')} · ${t('teacher.until', { date: fmt(b.expires_at) })}${typeof b.days_left === 'number' ? ` ${t('teacher.days_left', { n: b.days_left })}` : ''}`
    : b.status === 'past_due' ? t('teacher.past_due')
    : b.status === 'trial' ? t('teacher.trial') : t('teacher.inactive');
  const statusCls = active ? '' : b.status === 'past_due' ? 'bad' : 'muted';
  const seats = b.seats || 0;
  const breakdown = b.is_school
    ? (seats > 0
        ? t('teacher.billing_breakdown_seats', { base: b.base_usd, extra: b.per_extra_usd, n: seats, total: b.price_usd })
        : t('teacher.billing_breakdown_base', { base: b.base_usd }))
    : null;

  return (
    <div className="tch-card tch-billing">
      <div className="tch-billing-row">
        <div style={{ minWidth: 0 }}>
          <div className="tch-billing-title">{t('teacher.subscription', { price: b.price_usd })}</div>
          <div className={`tch-billing-status ${statusCls}`}>{statusLine}</div>
        </div>
        <button className="tch-btn sm" onClick={pay} disabled={busy}>
          {active ? t('teacher.renew') : t('teacher.pay', { price: b.price_usd })}
        </button>
      </div>

      {b.is_school && (
        <div className="tch-seats">
          <div className="tch-seats-label">
            {t('teacher.seats_label', { extra: b.per_extra_usd })}
            {b.teachers > 0 && <span className="tch-muted sm">{t('teacher.seats_now', { n: b.teachers })}</span>}
          </div>
          <div className="tch-seats-ctl">
            <button className="tch-seats-btn" onClick={() => changeSeats(-1)}
              disabled={busy || seats <= (b.teachers || 0)} aria-label={t('teacher.less')}>−</button>
            <span className="tch-seats-n">{seats}</span>
            <button className="tch-seats-btn" onClick={() => changeSeats(1)}
              disabled={busy || seats >= 50} aria-label={t('teacher.more')}>+</button>
          </div>
        </div>
      )}

      {breakdown && <div className="tch-billing-status muted" style={{ marginTop: 6 }}>{breakdown}</div>}
    </div>
  );
}

// Викладацька статистика: зведені KPI + детальний прогрес по ОБРАНИХ учнях
// (перевикористовує StudentPicker для вибору і StudentDetail для показу).
function TeacherStats({ students, onReload }) {
  const { t } = useT();
  const { role, ownerAsTeacher } = useRole();
  const { is_school } = useTenant();
  // Соло-репетитор (не-шкільний тенант) завжди платить за себе. У школі оплату
  // бачить лише власник (адмін) – не звичайний викладач і не власник у режимі
  // викладача (за доданих викладачів платить адміністратор).
  const showBilling = is_school ? (role === 'owner' && !ownerAsTeacher) : true;
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
          <p className="tch-muted">{t('teacher.stats_empty')}</p>
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
        <Kpi value={n} label={t('teacher.kpi_students')} />
        <Kpi value={active7} label={t('teacher.kpi_active7')} />
        <Kpi value={atRisk} label={t('teacher.kpi_at_risk')} warn={atRisk > 0} />
        <Kpi value={`${avgLearned}%`} label={t('teacher.kpi_avg_learned')} />
      </div>

      <div className="tch-card">
        <h3 className="tch-h3">{t('teacher.stats_by_student')}</h3>
        <p className="tch-muted sm">{t('teacher.stats_pick_hint')}</p>
        <StudentPicker students={students} selected={sel} onToggle={toggle} />
      </div>

      {[...sel].map((id) => (
        <StudentDetail key={id} studentId={id} onClose={() => toggle(id)}
                       onDeleted={() => { toggle(id); onReload?.(); }} />
      ))}

      {showBilling && <TeacherBilling />}
    </>
  );
}

export default function TeacherPage() {
  const { t } = useT();
  // Активна вкладка – з URL (?tab=), щоб нижня викладацька навігація й
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
            {t('teacher.forbidden')}</p></div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <AppBar showProLink={false} />
      <div className="tch-wrap">
        <div className="tch-top">
          <h2 className="tch-title">{t('teacher.title')}</h2>
          <div className="tch-top-actions">
            {view === 'decks' && mode === 'list' && (
              <button className="tch-btn" onClick={() => setMode('create')}>+ {t('teacher.deck_noun')}</button>
            )}
            {isOwner ? (
              <button className="tch-btn ghost sm" onClick={toggleOwnerMode}>
                {ownerAsTeacher ? `🛠 ${t('teacher.admin')}` : `👩‍🏫 ${t('teacher.as_teacher')}`}
              </button>
            ) : (
              <button className="tch-btn ghost sm" onClick={previewAsStudent}>👁 {t('teacher.as_student')}</button>
            )}
          </div>
        </div>

        {view === 'students' && <StudentsList />}
        {view === 'calendar' && <CalendarManager />}
        {view === 'stats' && (isOwnerSchool ? <SchoolStats /> : <TeacherStats students={students} onReload={load} />)}
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
            {decks === null && <p className="tch-muted">{t('teacher.loading')}</p>}
            {decks && decks.length === 0 && (
              <div className="tch-card">
                <p className="tch-muted">{t('teacher.no_decks')}</p>
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
                    {t('teacher.words_count', { n: d.word_count })} · {d.assign_to_all
                      ? t('teacher.assigned_all_short')
                      : t('teacher.assigned_n_students', { n: d.assignment.count ?? 0 })}
                  </div>
                </div>
                <span className="tch-deck-edit">{t('teacher.edit')}</span>
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
            {t('teacher.replay_onboarding')}
          </button>
        )}
      </div>
    </div>
  );
}
