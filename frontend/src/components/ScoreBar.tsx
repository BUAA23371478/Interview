import React from 'react';

interface ScoreBarProps {
  label: string;
  score: number;
  maxScore?: number;
  color?: string;
}

const ScoreBar: React.FC<ScoreBarProps> = ({
  label,
  score,
  maxScore = 100,
  color = 'bg-primary-500',
}) => {
  const percentage = Math.min((score / maxScore) * 100, 100);

  const getColorClass = (pct: number) => {
    if (pct >= 80) return 'bg-green-500';
    if (pct >= 60) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-600">{label}</span>
        <span className="text-sm font-semibold text-slate-800">{score}/{maxScore}</span>
      </div>
      <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color || getColorClass(percentage)}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

export default ScoreBar;
