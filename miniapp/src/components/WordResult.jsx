import { useT } from '../contexts/LangContext';
import { optimizeImage } from '../utils/optimizeImage';
import SpeakButton from './SpeakButton';
import WordPlaceholder from './WordPlaceholder';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱', de: '🇩🇪', fr: '🇫🇷' };

function WordResult({ data, nativeLang, targetLang }) {
  const { t, lang } = useT();
  const flag = FLAGS[nativeLang || lang] || '🌐';
  const speakLang = targetLang || data?.target_lang;

  const examples = Array.isArray(data?.examples)
    ? data.examples.map(e => typeof e === 'string' ? { sentence: e, explanation: '' } : e)
    : [];

  return (
    <div className="word-result">
      <div className="snap-result-head">
        {data.image_url ? (
          <img src={optimizeImage(data.image_url)} alt="" className="snap-result-img" loading="lazy" />
        ) : (
          <WordPlaceholder word={data.word} className="snap-result-img" />
        )}
        <div className="snap-result-body">
          <div className="snap-result-meta">
            {data.part_of_speech && <span>{data.part_of_speech}</span>}
            {data.part_of_speech && data.difficulty && <span className="dot">·</span>}
            {data.difficulty && <span>{data.difficulty}</span>}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="snap-result-word">{data.word}</div>
            <SpeakButton text={data.word} lang={speakLang} size="sm" />
          </div>
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
