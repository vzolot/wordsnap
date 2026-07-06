import { useCallback, useEffect, useState } from 'react';
import AppBar from '../components/AppBar';
import {
  getTeacherDecks, getTeacherStudents, getTeacherDeck,
  createTeacherDeck, updateTeacherDeck, getTeacherStudentDetail,
} from '../api/client';

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
  const [assignAll, setAssignAll] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const toggle = (id) => setSelected((prev) => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const submit = async () => {
    setErr('');
    if (!title.trim()) { setErr('Вкажіть назву колоди'); return; }
    if (!text.trim()) { setErr('Додайте слова: «слово - переклад» по рядку'); return; }
    setBusy(true);
    try {
      const r = await createTeacherDeck({
        title: title.trim(),
        text,
        assign_to_all: assignAll,
        assignee_user_ids: assignAll ? null : [...selected],
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
      <div className="tch-toggle-row">
        <button
          className={`tch-pill ${assignAll ? 'on' : ''}`}
          onClick={() => setAssignAll(true)}
        >Всім учням</button>
        <button
          className={`tch-pill ${!assignAll ? 'on' : ''}`}
          onClick={() => setAssignAll(false)}
        >Обраним учням</button>
      </div>
      {!assignAll && (
        <StudentPicker students={students} selected={selected} onToggle={toggle} />
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
    <div className="tch-card"><p className="tch-muted">
      Ще немає учнів. Поділіться посиланням на бота.</p></div>
  );

  return (
    <>
      {students.map((s) => (
        <button key={s.id} className="tch-deck" onClick={() => setSel(s.id)}>
          <div className="tch-deck-main">
            <div className="tch-deck-title">
              {s.display_name}{s.at_risk && <span className="tch-risk">в ризику</span>}
            </div>
            <div className="tch-deck-sub">
              🔥 {s.streak} · {s.reviews_7d} за 7д · {s.learned_pct}% вивчено · {relTime(s.last_visit)}
            </div>
          </div>
          <span className="tch-deck-edit">›</span>
        </button>
      ))}
    </>
  );
}

export default function TeacherPage() {
  const [decks, setDecks] = useState(null);
  const [students, setStudents] = useState([]);
  const [mode, setMode] = useState('list'); // list | create | edit
  const [editId, setEditId] = useState(null);
  const [forbidden, setForbidden] = useState(false);
  const [view, setView] = useState('decks'); // decks | students

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
          {view === 'decks' && mode === 'list' && (
            <button className="tch-btn" onClick={() => setMode('create')}>+ Колода</button>
          )}
        </div>

        <div className="tch-toggle-row">
          <button className={`tch-pill ${view === 'decks' ? 'on' : ''}`}
                  onClick={() => { setView('decks'); setMode('list'); }}>Колоди</button>
          <button className={`tch-pill ${view === 'students' ? 'on' : ''}`}
                  onClick={() => setView('students')}>Учні</button>
        </div>

        {view === 'students' && <StudentsList />}

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
