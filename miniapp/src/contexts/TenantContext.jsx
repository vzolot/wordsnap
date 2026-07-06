import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getTenantConfig } from '../api/client';

/**
 * White-label бренд тенанта. Тягне /api/tenant/config при старті, застосовує
 * кольори бренду як CSS-змінні і віддає прапори (billing-UI, AI-снап) усьому
 * додатку. tenant_id обчислюється на бекенді з підпису бота — клієнт не впливає.
 *
 * Для тенанта id=1 (WordSnap) конфіг повертає дефолтний бренд/кольори і
 * billing_ui_enabled=true, тож поведінка й вигляд не змінюються.
 */

const DEFAULTS = {
  tenant_id: 1,
  slug: 'wordsnap',
  display_name: 'WordSnap',
  logo_url: null,
  color_primary: '#7C3AED',
  color_accent: '#EC4899',
  ai_snap_available: true,
  billing_ui_enabled: true,
};

const CACHE_KEY = 'wordsnap.tenant_config';

function readCachedConfig() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch { /* noop */ }
  return DEFAULTS;
}

// #RRGGBB → {r,g,b}
function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || '').trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function rgba(hex, a) {
  const c = hexToRgb(hex);
  if (!c) return null;
  return `rgba(${c.r}, ${c.g}, ${c.b}, ${a})`;
}

function darken(hex, factor) {
  const c = hexToRgb(hex);
  if (!c) return hex;
  const d = (v) => Math.max(0, Math.round(v * (1 - factor)));
  const h = (v) => d(v).toString(16).padStart(2, '0');
  return `#${h(c.r)}${h(c.g)}${h(c.b)}`;
}

/** Перезаписує брендові CSS-змінні (App.css :root використовує --violet/--pink/
 *  --gradient та похідні). Для дефолтного бренду значення збігаються — no-op. */
function applyBrand(primary, accent) {
  const root = document.documentElement;
  const set = (k, v) => { if (v) root.style.setProperty(k, v); };
  set('--violet', primary);
  set('--violet-dark', darken(primary, 0.25));
  set('--violet-soft', rgba(primary, 0.10));
  set('--pink', accent);
  set('--pink-soft', rgba(accent, 0.10));
  set('--gradient', `linear-gradient(135deg, ${primary} 0%, ${accent} 100%)`);
  set('--gradient-soft', `linear-gradient(135deg, ${rgba(primary, 0.08)}, ${rgba(accent, 0.08)})`);
}

const TenantContext = createContext(DEFAULTS);

export function TenantProvider({ children }) {
  const [config, setConfig] = useState(() => {
    const c = readCachedConfig();
    applyBrand(c.color_primary, c.color_accent); // миттєвий бренд з кешу
    return c;
  });

  useEffect(() => {
    let alive = true;
    getTenantConfig()
      .then((r) => {
        if (!alive || !r?.data) return;
        const c = { ...DEFAULTS, ...r.data };
        applyBrand(c.color_primary, c.color_accent);
        setConfig(c);
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(c)); } catch { /* noop */ }
      })
      .catch(() => { /* лишаємо кеш/дефолт */ });
    return () => { alive = false; };
  }, []);

  const value = useMemo(() => ({
    ...config,
    billingEnabled: !!config.billing_ui_enabled,
    aiSnapAvailable: config.ai_snap_available !== false,
    isDefaultTenant: config.tenant_id === 1,
  }), [config]);

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant() {
  return useContext(TenantContext);
}
