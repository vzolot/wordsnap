import { NavLink, useLocation } from 'react-router-dom';
import { useT } from '../contexts/LangContext';
import { useTenant } from '../contexts/TenantContext';
import { useRole } from '../contexts/RoleContext';
import './NavBar.css';

const Icon = ({ d }) => (
  <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const ICONS = {
  home:   'M3 11.5L12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z',
  songs:  'M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  themes: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16zM3.27 6.96L12 12.01l8.73-5.05M12 22.08V12',
  book:   'M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 1 4 17.5zM4 17.5A2.5 2.5 0 0 1 6.5 20H20',
  review: 'M21 12a9 9 0 1 1-3.5-7.1M21 4v5h-5',
  stats:  'M3 21h18M5 21V10M11 21V4M17 21v-7',
  users:  'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  lessons: 'M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
  school: 'M3 21h18M5 21V8l7-4 7 4v13M9 21v-5a3 3 0 0 1 6 0v5',
};

// Викладацька навігація. Активна вкладка – за ?tab= (усі ведуть на /teacher).
// У школі додається вкладка «Школа». Верхніх пігулок більше немає – усе тут.
const BASE_TEACHER_TABS = [
  { tab: 'students', icon: ICONS.users,   key: 'teacher.tab.students' },
  { tab: 'decks',    icon: ICONS.book,    key: 'teacher.tab.decks' },
  { tab: 'calendar', icon: ICONS.lessons, key: 'teacher.tab.calendar' },
  { tab: 'stats',    icon: ICONS.stats,   key: 'teacher.tab.stats' },
];

const OWNER_TABS = [
  { tab: 'school',   icon: ICONS.school,  key: 'teacher.tab.school' },
  { tab: 'calendar', icon: ICONS.lessons, key: 'teacher.tab.calendar' },
  { tab: 'decks',    icon: ICONS.book,    key: 'teacher.tab.decks' },
  { tab: 'stats',    icon: ICONS.stats,   key: 'teacher.tab.stats' },
];

function TeacherNav() {
  const { t } = useT();
  const loc = useLocation();
  const { is_school } = useTenant();
  const { role, ownerAsTeacher } = useRole();
  const onTeacher = loc.pathname === '/teacher';
  // Власник школи керує → без «Учні» (це у «Школа»); порядок Школа/Календар/…
  // У «режимі викладача» власник отримує звичайну викладацьку навігацію.
  const isOwnerSchool = is_school && role === 'owner' && !ownerAsTeacher;
  const tabs = isOwnerSchool ? OWNER_TABS : BASE_TEACHER_TABS;
  const defaultTab = isOwnerSchool ? 'school' : 'students';
  const tab = new URLSearchParams(loc.search).get('tab') || defaultTab;
  return (
    <nav className="navbar">
      {tabs.map((it) => (
        <NavLink
          key={it.tab}
          to={`/teacher?tab=${it.tab}`}
          className={onTeacher && tab === it.tab ? 'nav-item active' : 'nav-item'}
        >
          <Icon d={it.icon} />
          <span className="nav-label">{t(it.key)}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function NavBar() {
  const { t } = useT();
  const { isDefaultTenant } = useTenant();
  const { teacherMode } = useRole();

  // Викладач (не в режимі «перегляд як учень») → окремий викладацький таб-бар.
  if (teacherMode) return <TeacherNav />;

  const items = [
    { to: '/',       key: 'nav.home',   icon: ICONS.home,  label: null },
    { to: '/songs',  key: 'nav.songs',  icon: ICONS.songs, label: null },
    { to: '/themes', key: 'nav.themes', icon: ICONS.themes, label: null },
    { to: '/words',  key: 'nav.words',  icon: ICONS.book,  label: null },
    { to: '/stats',  key: 'nav.stats',  icon: ICONS.stats, label: null },
  ];
  if (!isDefaultTenant) {
    // White-label учень: «Пісні» → «Уроки» (бронювання уроків із викладачем).
    items.splice(1, 1);
    items.push({ to: '/lessons', key: 'nav.lessons', icon: ICONS.lessons, label: null });
  }

  return (
    <nav className="navbar">
      {items.map(it => (
        <NavLink key={it.to} to={it.to} end={it.to === '/'} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
          <Icon d={it.icon} />
          <span className="nav-label">{it.label || t(it.key)}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export default NavBar;
