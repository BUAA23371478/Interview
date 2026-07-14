import React from 'react';
import {
  Radar,
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from 'recharts';
import type { DimensionScores } from '@/types/interview';

interface RadarChartProps {
  scores: DimensionScores;
}

const RadarChartView: React.FC<RadarChartProps> = ({ scores }) => {
  const data = [
    { dimension: '技术深度', score: scores.techDepth, fullMark: 100 },
    { dimension: '表达清晰度', score: scores.clarity, fullMark: 100 },
    { dimension: '逻辑性', score: scores.logic, fullMark: 100 },
    { dimension: '岗位匹配度', score: scores.jobMatch, fullMark: 100 },
  ];

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
      <h4 className="font-semibold text-slate-800 mb-2 text-center">各维度评分</h4>
      <div className="w-full h-72 sm:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsRadar cx="50%" cy="50%" outerRadius="70%" data={data}>
            <PolarGrid stroke="#e2e8f0" />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: '#64748b', fontSize: 13, fontWeight: 500 }}
            />
            <PolarRadiusAxis
              angle={45}
              domain={[0, 100]}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
            />
            <Radar
              name="评分"
              dataKey="score"
              stroke="#3b82f6"
              fill="#3b82f6"
              fillOpacity={0.25}
              strokeWidth={2}
            />
          </RechartsRadar>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default RadarChartView;
