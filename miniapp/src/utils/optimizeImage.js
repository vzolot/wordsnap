// Стискаємо Unsplash URL до розміру картки. Старі рядки в БД мають
// .../photo-XXXX?...&ixid=...&w=1080 – добавляємо/перевизначаємо
// w/q/fmt параметри щоб не качати 200-400KB на мобілку.
//
// Не-Unsplash URL'и (наприклад згенеровані OpenAI зображення) – повертаємо
// як є, бо вони вже оптимізовані.

const UNSPLASH_HOST = 'images.unsplash.com';

export function optimizeImage(url) {
  if (!url || typeof url !== 'string') return url;
  if (!url.includes(UNSPLASH_HOST)) return url;

  try {
    const u = new URL(url);
    // Перевизначаємо тільки якщо параметра w нема або він >600
    const currentW = parseInt(u.searchParams.get('w') || '0', 10);
    if (currentW === 0 || currentW > 600) u.searchParams.set('w', '600');

    if (!u.searchParams.has('h')) u.searchParams.set('h', '400');
    if (!u.searchParams.has('fit')) u.searchParams.set('fit', 'crop');
    if (!u.searchParams.has('auto')) u.searchParams.set('auto', 'format');

    const currentQ = parseInt(u.searchParams.get('q') || '0', 10);
    if (currentQ === 0 || currentQ > 80) u.searchParams.set('q', '75');

    return u.toString();
  } catch {
    return url;
  }
}
