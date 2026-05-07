// Базовий блок-скелет з shimmer-анімацією. Використовується для побудови
// page-specific skeletons (HomeSkeleton, WordsSkeleton, ...).
export function SkeletonBox({ width, height, radius = 12, className = '', style = {} }) {
  return (
    <div
      className={`skeleton-box ${className}`}
      style={{
        width: width ?? '100%',
        height,
        borderRadius: radius,
        ...style,
      }}
      aria-hidden="true"
    />
  );
}

export function HomeSkeleton() {
  return (
    <div className="page" aria-busy="true">
      {/* Streak card */}
      <SkeletonBox height={130} radius={20} style={{ marginBottom: 14 }} />
      {/* Snap card */}
      <SkeletonBox height={170} radius={20} style={{ marginBottom: 14 }} />
      {/* 3 stat tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        <SkeletonBox height={86} radius={16} />
        <SkeletonBox height={86} radius={16} />
        <SkeletonBox height={86} radius={16} />
      </div>
    </div>
  );
}

export function WordsSkeleton({ rows = 6 }) {
  return (
    <div className="page" aria-busy="true">
      <SkeletonBox height={28} width="40%" style={{ marginBottom: 16 }} />
      <SkeletonBox height={36} radius={999} style={{ marginBottom: 14 }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonBox key={i} height={68} radius={14} />
        ))}
      </div>
    </div>
  );
}

export function StatsSkeleton() {
  return (
    <div className="page" aria-busy="true">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14, gap: 10 }}>
        <SkeletonBox height={32} width="40%" />
        <SkeletonBox height={32} width={120} radius={999} />
      </div>
      <SkeletonBox height={140} radius={20} style={{ marginBottom: 14 }} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonBox key={i} height={70} radius={16} />
        ))}
      </div>
      <SkeletonBox height={200} radius={16} />
    </div>
  );
}

export function LeaderboardSkeleton({ rows = 8 }) {
  return (
    <div className="page" aria-busy="true">
      <SkeletonBox height={28} width="40%" style={{ marginBottom: 8 }} />
      <SkeletonBox height={16} width="70%" style={{ marginBottom: 18 }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonBox key={i} height={52} radius={12} />
        ))}
      </div>
    </div>
  );
}

export function ReviewSkeleton() {
  return (
    <div className="page" aria-busy="true">
      <SkeletonBox height={36} radius={999} style={{ marginBottom: 16 }} />
      <SkeletonBox height={6} radius={3} style={{ marginBottom: 18 }} />
      <SkeletonBox height={380} radius={20} />
    </div>
  );
}
