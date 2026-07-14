import React from 'react';
import { Star } from 'lucide-react';

interface DifficultyBadgeProps {
  difficulty: number;
  questionIndex: number;
  consecutiveCorrect: number;
  consecutiveWrong: number;
}

const DIFFICULTY_LABELS: Record<number, string> = {
  1: '入门',
  2: '基础',
  3: '中等',
  4: '进阶',
  5: '专家',
};

const DifficultyBadge: React.FC<DifficultyBadgeProps> = ({
  difficulty,
  questionIndex,
  consecutiveCorrect,
  consecutiveWrong,
}) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-500">当前难度：</span>
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((level) => (
            <Star
              key={level}
              className={`w-4 h-4 ${
                level <= difficulty
                  ? 'text-yellow-400 fill-yellow-400'
                  : 'text-slate-200'
              }`}
            />
          ))}
        </div>
        <span className="text-sm font-medium text-slate-700">
          {DIFFICULTY_LABELS[difficulty]}
        </span>
      </div>

      <div className="flex items-center gap-4 text-sm">
        <span className="text-slate-400">
          第 <span className="font-semibold text-slate-700">{questionIndex}</span> 题
        </span>
        {consecutiveCorrect >= 3 && (
          <span className="flex items-center gap-1 text-green-600">
            <span className="w-2 h-2 bg-green-500 rounded-full" />
            连续答对 {consecutiveCorrect} 题
          </span>
        )}
        {consecutiveWrong >= 2 && (
          <span className="flex items-center gap-1 text-orange-500">
            <span className="w-2 h-2 bg-orange-500 rounded-full" />
            连续答错 {consecutiveWrong} 题
          </span>
        )}
      </div>
    </div>
  );
};

export default DifficultyBadge;
