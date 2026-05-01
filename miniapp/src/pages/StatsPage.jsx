import { useEffect, useState } from 'react';
import { getStats } from '../api/client';

function StatsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStats().then(r => {
      setStats(r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="page"><p style={{color:'var(--hint)',textAlign:'center'}}>Завантаження...</p></div>;

  return (
    <div className="page">
      <h1 style={{fontSize: 22, fontWeight: 700, marginBottom: 16}}>📊 Статистика</h1>

      <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:12}}>
        {[
          {label:'Всього слів', value: stats?.total_words || 0, icon:'📖'},
          {label:'Вивчено', value: stats?.learned_words || 0, icon:'✅'},
          {label:'Повторено сьогодні', value: stats?.reviewed_today || 0, icon:'🔄'},
          {label:'Серія днів', value: stats?.streak || 0, icon:'🔥'},
        ].map(item => (
          <div key={item.label} className="card" style={{textAlign:'center'}}>
            <p style={{fontSize:28}}>{item.icon}</p>
            <p style={{fontSize:24,fontWeight:700,marginTop:4}}>{item.value}</p>
            <p style={{color:'var(--hint)',fontSize:12,marginTop:2}}>{item.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default StatsPage;
