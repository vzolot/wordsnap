import { NavLink } from 'react-router-dom';
import './NavBar.css';

function NavBar() {
  return (
    <nav className="navbar">
      <NavLink to="/" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
        <span className="nav-icon">🏠</span>
        <span className="nav-label">Головна</span>
      </NavLink>
      <NavLink to="/words" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
        <span className="nav-icon">📚</span>
        <span className="nav-label">Слова</span>
      </NavLink>
      <NavLink to="/review" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
        <span className="nav-icon">🔄</span>
        <span className="nav-label">Повторення</span>
      </NavLink>
      <NavLink to="/stats" className={({isActive}) => isActive ? 'nav-item active' : 'nav-item'}>
        <span className="nav-icon">📊</span>
        <span className="nav-label">Статистика</span>
      </NavLink>
    </nav>
  );
}

export default NavBar;
