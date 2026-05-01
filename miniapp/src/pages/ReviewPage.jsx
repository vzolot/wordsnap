import { useEffect, useState } from 'react';
import { getReviewWords, submitReview } from '../api/client';

function ReviewPage() {
  const [words, setWords] = useState([]);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);

  useEffect(() => {
    getReviewWords().then(r => {
      setWords(r.data || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const current = words[index];

  const handleAnswer = async (quality) => {
    await submitReview(current.id, quality).catch(() => {});
    if (index + 1 >= words.length) {
      setDone(true);
    } else {
      setIndex(i => i + 1);
      setFlipped(false);
    }
  };

  if (loading) return <div className="page"><p style={{color:'var(--hint)',textAlign:'center'}}>Завантаження...</p></div>;
  if (done || words.length === 0) return (
    <div className="page" style={{textAlign:'center',paddingTop:60}}>
      <p style={{fontSize:48}}>🎉</p>
      <h2 style={{marginTop:16}}>Молодець!</h2>
      <p style={{color:'var(--hint)',marginTop:8}}>Повторення завершено</p>
    </div>
  );

  return (
    <div className="page">
      <p style={{color:'var(--hint)',marginBottom:16}}>{index + 1} / {words.length}</p>

      <div onClick={() => setFlipped(f => !f)} className="card" style={{
        minHeight: 200, display:'flex', flexDirection:'column',
        alignItems:'center', justifyContent:'center', cursor:'pointer',
        background: flipped ? 'rgba(108,99,255,0.15)' : 'var(--card-bg)'
      }}>
        <p style={{fontSize: 28, fontWeight: 700, textAlign:'center'}}>
          {flipped ? current.translation : current.word}
        </p>
        {!flipped && <p style={{color:'var(--hint)',marginTop:12,fontSize:13}}>Натисни щоб побачити переклад</p>}
        {flipped && current.example && (
          <p style={{color:'var(--hint)',marginTop:12,fontSize:13,textAlign:'center',fontStyle:'italic'}}>
            {current.example}
          </p>
        )}
      </div>

      {flipped && (
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, marginTop:16}}>
          <button className="btn secondary" onClick={() => handleAnswer(1)}>😓 Важко</button>
          <button className="btn secondary" onClick={() => handleAnswer(3)}>🤔 Нормально</button>
          <button className="btn" onClick={() => handleAnswer(5)}>😊 Легко</button>
        </div>
      )}
    </div>
  );
}

export default ReviewPage;
