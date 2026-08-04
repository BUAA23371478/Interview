// 技能雷达图：SVG 六边形（参考 interview-practice 的 radar chart）
export default function RadarChart({ scores }: { scores: Record<string, number> }) {
  const labels = Object.keys(scores)
  const values = labels.map((k) => Math.min(10, Number(scores[k]) || 0))
  const n = Math.max(labels.length, 3)
  const center = 100
  const radius = 70

  function point(i: number, r: number): [number, number] {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / n
    return [center + r * Math.cos(angle), center + r * Math.sin(angle)]
  }

  const grid = [0.3, 0.6, 1.0].map((f) =>
    Array.from({ length: n }, (_, i) => point(i, radius * f).join(',')).join(' '),
  )

  const dataPoly = Array.from({ length: n }, (_, i) => point(i, (radius * values[i]) / 10).join(',')).join(' ')

  return (
    <svg viewBox="0 0 200 200" className="w-full h-full">
      <defs>
        <linearGradient id="radarGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#667eea" />
          <stop offset="100%" stopColor="#764ba2" />
        </linearGradient>
      </defs>
      {grid.map((pts, i) => (
        <polygon key={i} points={pts} fill="none" stroke="#e5e7eb" strokeWidth="1" />
      ))}
      {Array.from({ length: n }, (_, i) => {
        const [x, y] = point(i, radius)
        return <line key={i} x1={center} y1={center} x2={x} y2={y} stroke="#e5e7eb" strokeWidth="1" />
      })}
      <polygon points={dataPoly} fill="url(#radarGrad)" opacity="0.7" />
      {labels.map((label, i) => {
        const [x, y] = point(i, radius + 18)
        return (
          <text key={label} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize="9" fill="#6b7280">
            {label}
          </text>
        )
      })}
    </svg>
  )
}
