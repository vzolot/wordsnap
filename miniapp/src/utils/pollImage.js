import { getWords } from '../api/client';

// Бекенд зберігає слово без картинки і довантажує її з Unsplash у фоні.
// Цей хелпер кілька разів пуллить /api/words, щоб юзер побачив картинку
// одразу на тій же карточці без необхідності переходити в Words tab.
//
// onFound(url) – викликається з URL коли картинка зʼявилась.
// isCancelled() – повертає true, щоб перервати (на unmount, новий submit,
// reset тощо).
export async function pollImage(wordId, onFound, isCancelled = () => false) {
  const delays = [1500, 2500, 3500];
  for (const d of delays) {
    await new Promise(r => setTimeout(r, d));
    if (isCancelled()) return;
    try {
      const r = await getWords();
      if (isCancelled()) return;
      const found = (r.data || []).find(w => w.id === wordId);
      if (found?.image_url) {
        onFound(found.image_url);
        return;
      }
    } catch { /* try again next tick */ }
  }
}
