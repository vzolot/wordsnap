import { useT } from '../contexts/LangContext';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱', de: '🇩🇪' };

function WordResult({ data, nativeLang }) {
  const { t, lang } = useT();
  const flag = FLAGS[nativeLang || lang] || '🌐';

  const examples = Array.isArray(data?.examples)
    ? data.examples.map(e => typeof e === 'string' ? { sentence: e, explanation: '' } : e)
    : [];

  return (
    <div className="word-result">
      <div className="snap-result-head">
        {data.image_url ? (
          <img src={data.image_url} alt="" className="snap-result-img" />
        ) : (
          <div className="snap-result-img" style={{ display: 'grid', placeItems: 'center', fontSize: 30 }}>📸</div>
        )}
        <div className="snap-result-body">
          <div className="snap-result-meta">
            {data.part_of_speech && <span>{data.part_of_speech}</span>}
            {data.part_of_speech && data.difficulty && <span className="dot">·</span>}
            {data.difficulty && <span>{data.difficulty}</span>}
          </div>
          <div className="snap-result-word">{data.word}</div>
          <div className="snap-result-translation">{flag} {data.translation}</div>
        </div>
      </div>

      {examples.length > 0 && (
        <>
          <div className="snap-section-label">{t('snap.examples')}</div>
          {examples.slice(0, 3).map((ex, i) => (
            <div key={i} className="snap-example-item">
              <span className="snap-example-num">{i + 1}.</span>
              <span className="snap-example-sentence">{ex.sentence}</span>
              {ex.explanation && (
                <span className="snap-example-explanation">→ {ex.explanation}</span>
              )}
            </div>
          ))}
        </>
      )}

      {data.memory_tip && (
        <div className="snap-tip">
          💡 <span>{data.memory_tip}</span>
        </div>
      )}
    </div>
  );
}

export default WordResult;
