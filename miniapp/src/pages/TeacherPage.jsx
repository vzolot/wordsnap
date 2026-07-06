import { useCallback, useEffect, useState } from 'react';
import AppBar from '../components/AppBar';
import {
  getTeacherDecks, getTeacherStudents, getTeacherDeck,
  createTeacherDeck, updateTeacherDeck,
} from '../api/client';

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

export default function TeacherPage() {
  const [decks, setDecks] = useState(null);
  const [students, setStudents] = useState([]);
  const [mode, setMode] = useState('list'); // list | create | edit
  const [editId, setEditId] = useState(null);
  const [forbidden, setForbidden] = useState(false);

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
          {mode === 'list' && (
            <button className="tch-btn" onClick={() => setMode('create')}>+ Колода</button>
          )}
        </div>

        {mode === 'create' && (
          <CreateDeckForm
            students={students}
            onCreated={() => { setMode('list'); load(); }}
            onCancel={() => setMode('list')}
          />
        )}

        {mode === 'edit' && editId != null && (
          <EditDeck
            deckId={editId}
            students={students}
            onClose={() => { setEditId(null); setMode('list'); load(); }}
          />
        )}

        {mode === 'list' && (
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
