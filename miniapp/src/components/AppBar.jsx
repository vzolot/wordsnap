import { Link } from 'react-router-dom';

function AppBar({ showProLink = true, isPro = false }) {
  return (
    <header className="app-bar">
      <div className="app-bar-logo">W</div>
      <div>
        <div className="app-bar-title">WordSnap</div>
        <div className="app-bar-sub">mini app</div>
      </div>
      {showProLink && (
        isPro ? (
          <span className="pro-active-badge" style={{ marginLeft: 'auto' }}>✨ PRO</span>
        ) : (
          <Link to="/pro" className="app-bar-pro">✨ Pro</Link>
        )
      )}
    </header>
  );
}

export default AppBar;
