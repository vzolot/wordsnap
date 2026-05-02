import { NavLink } from 'react-router-dom';
import { useT } from '../contexts/LangContext';
import './NavBar.css';

const Icon = ({ d }) => (
  <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const ICONS = {
  home:   'M3 11.5L12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z',
  book:   'M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 1 4 17.5zM4 17.5A2.5 2.5 0 0 1 6.5 20H20',
  review: 'M21 12a9 9 0 1 1-3.5-7.1M21 4v5h-5',
  stats:  'M3 21h18M5 21V10M11 21V4M17 21v-7',
};

function NavBar() {
  const { t } = useT();
  const items = [
    { to: '/',       key: 'nav.home',   icon: ICONS.home },
    { to: '/words',  key: 'nav.words',  icon: ICONS.book },
    { to: '/review', key: 'nav.review', icon: ICONS.review },
    { to: '/stats',  key: 'nav.stats',  icon: ICONS.stats },
  ];

  return (
    <nav className="navbar">
      {items.map(it => (
        <NavLink key={it.to} to={it.to} end={it.to === '/'} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
          <Icon d={it.icon} />
          <span className="nav-label">{t(it.key)}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export default NavBar;
