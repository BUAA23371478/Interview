import React from 'react';
import { CheckCircle, XCircle, Lightbulb, AlertTriangle, BookOpen } from 'lucide-react';
import type { Feedback } from '@/types/practice';
import MarkdownContent from '@/utils/markdown';

interface FeedbackPanelProps {
  feedback: Feedback;
}

const FeedbackPanel: React.FC<FeedbackPanelProps> = ({ feedback }) => {
  const { score, isCorrect, correctAnswer, analysis, knowledgePoints, commonMistakes } = feedback;

  const getScoreColor = (s: number) => {
    if (s >= 80) return 'text-green-600';
    if (s >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getScoreBg = (s: number) => {
    if (s >= 80) return 'bg-green-50 border-green-200';
    if (s >= 60) return 'bg-yellow-50 border-yellow-200';
    return 'bg-red-50 border-red-200';
  };

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Score Banner */}
      <div className={`flex items-center gap-4 p-5 rounded-2xl border ${getScoreBg(score)}`}>
        <div className="flex-shrink-0">
          {isCorrect ? (
            <CheckCircle className="w-10 h-10 text-green-500" />
          ) : (
            <XCircle className="w-10 h-10 text-red-500" />
          )}
        </div>
        <div className="flex-1">
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-bold ${getScoreColor(score)}`}>{score}</span>
            <span className="text-slate-500 text-sm">/ 100 分</span>
          </div>
          <p className={`text-sm font-medium mt-0.5 ${getScoreColor(score)}`}>
            {score >= 80 ? '回答优秀！' : score >= 60 ? '基本正确，还有提升空间' : '需要加强学习'}
          </p>
        </div>
      </div>

      {/* Reference Answer */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
        <div className="flex items-center gap-2 mb-3">
          <BookOpen className="w-5 h-5 text-primary-500" />
          <h4 className="font-semibold text-slate-800">参考答案</h4>
        </div>
        <MarkdownContent content={correctAnswer} />
      </div>

      {/* Analysis */}
      {analysis && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-3">
            <Lightbulb className="w-5 h-5 text-yellow-500" />
            <h4 className="font-semibold text-slate-800">解题思路</h4>
          </div>
          <MarkdownContent content={analysis} />
        </div>
      )}

      {/* Knowledge Points */}
      {knowledgePoints && knowledgePoints.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
          <h4 className="font-semibold text-slate-800 mb-3">📚 考察知识点</h4>
          <div className="flex flex-wrap gap-2">
            {knowledgePoints.map((kp, i) => (
              <span
                key={i}
                className="px-3 py-1 text-sm bg-primary-50 text-primary-700 rounded-full border border-primary-200"
              >
                {kp}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Common Mistakes */}
      {commonMistakes && commonMistakes.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-5 h-5 text-orange-500" />
            <h4 className="font-semibold text-slate-800">常见错误</h4>
          </div>
          <ul className="space-y-2">
            {commonMistakes.map((mistake, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                <span className="text-orange-400 mt-0.5">⚠</span>
                {mistake}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default FeedbackPanel;
