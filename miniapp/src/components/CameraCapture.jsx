import { useEffect, useRef, useState } from 'react';

// File/Blob → base64 (без data-URL префіксу) + mime.
function blobToB64(fileOrBlob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = String(r.result);
      resolve({ b64: s.slice(s.indexOf(',') + 1), mime: fileOrBlob.type || 'image/jpeg' });
    };
    r.onerror = reject;
    r.readAsDataURL(fileOrBlob);
  });
}

/**
 * Жива камера прямо в додатку: getUserMedia → прев'ю → «Зняти» кадр у base64.
 * Викликає onCapture(b64, 'image/jpeg'). Працює на десктопі (вебкамера) і в
 * мобільних webview, що дозволяють камеру. Якщо живий доступ недоступний —
 * фолбек на нативну камеру пристрою через <input capture="environment">.
 * Потік камери ЗАВЖДИ зупиняємо при закритті (щоб не лишати індикатор увімкненим).
 */
export default function CameraCapture({ onCapture, onClose, busy }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [err, setErr] = useState('');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setErr('Жива камера недоступна в цьому клієнті.');
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } }, audio: false,
        });
        if (!alive) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
        setReady(true);
      } catch {
        setErr('Немає дозволу на камеру (або камери немає).');
      }
    })();
    return () => {
      alive = false;
      const s = streamRef.current;
      if (s) s.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const shoot = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement('canvas');
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext('2d').drawImage(v, 0, 0);
    const url = c.toDataURL('image/jpeg', 0.85);
    onCapture(url.slice(url.indexOf(',') + 1), 'image/jpeg');
  };

  const onFallbackFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    const { b64, mime } = await blobToB64(f);
    onCapture(b64, mime);
  };

  return (
    <div className="cam-overlay" role="dialog" aria-modal="true">
      <div className="cam-box">
        {err ? (
          <div className="cam-fallback">
            <p className="tch-muted">{err}</p>
            <label className="tch-btn">
              📷 Камера пристрою
              <input type="file" accept="image/*" capture="environment" hidden
                     onChange={onFallbackFile} disabled={busy} />
            </label>
          </div>
        ) : (
          <video ref={videoRef} className="cam-video" playsInline muted />
        )}
        <div className="cam-actions">
          <button className="tch-btn ghost" onClick={onClose} disabled={busy}>Закрити</button>
          {!err && (
            <button className="tch-btn" onClick={shoot} disabled={!ready || busy}>
              {busy ? 'Розпізнаю…' : '📸 Зняти'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
