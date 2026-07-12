import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getStats, readCache } from '../api/client';

/**
 * Роль поточного користувача → окрема оболонка для викладача.
 *
 * teacherMode = користувач teacher/owner І не увімкнув «перегляд як учень».
 * У цьому режимі App показує викладацький layout (Учні/Колоди/Календар/
 * Статистика) замість учнівського. studentPreview дозволяє викладачу тимчасово
 * побачити досвід учня (скидається в межах сесії).
 *
 * Роль беремо з /api/stats (там є `role`) — миттєво з кешу, потім освіжаємо.
 */

const RoleContext = createContext({
  role: null, isTeacher: false, teacherMode: false,
  studentPreview: false, setStudentPreview: () => {},
});

const PREVIEW_KEY = 'wordsnap.teacher_preview';

export function RoleProvider({ children }) {
  const [role, setRole] = useState(() => readCache('stats', { ignoreTtl: true })?.role || null);
  const [studentPreview, setPreviewState] = useState(() => {
    try { return sessionStorage.getItem(PREVIEW_KEY) === '1'; } catch { return false; }
  });

  useEffect(() => {
    let alive = true;
    getStats().then((r) => { if (alive && r?.data?.role) setRole(r.data.role); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const setStudentPreview = useCallback((v) => {
    setPreviewState(v);
    try {
      if (v) sessionStorage.setItem(PREVIEW_KEY, '1');
      else sessionStorage.removeItem(PREVIEW_KEY);
    } catch { /* noop */ }
  }, []);

  const isTeacher = role === 'teacher' || role === 'owner';
  const value = useMemo(() => ({
    role,
    isTeacher,
    teacherMode: isTeacher && !studentPreview,
    studentPreview: isTeacher && studentPreview,
    setStudentPreview,
  }), [role, isTeacher, studentPreview, setStudentPreview]);

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole() {
  return useContext(RoleContext);
}
