// Брендовий placeholder коли у слова ще немає картинки з Unsplash.
// Замість generic 📸-emoji показує градієнт + першу літеру слова —
// виглядає premium як в Notion/Linear.
function WordPlaceholder({ word, className = '', style = {} }) {
  const initial = (String(word || '?').trim().charAt(0) || '?').toUpperCase();
  return (
    <div className={`word-placeholder ${className}`.trim()} style={style}>
      <span className="word-placeholder-letter">{initial}</span>
    </div>
  );
}

export default WordPlaceholder;
