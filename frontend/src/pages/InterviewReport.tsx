import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Star, TrendingUp, AlertTriangle, Lightbulb, MessageSquare } from 'lucide-react';
import { interviewApi } from '@/api/interview';
import type { InterviewReport as InterviewReportType } from '@/types/interview';
import ScoreBar from '@/components/ScoreBar';
import RadarChartView from '@/components/RadarChart';
import LoadingDots from '@/components/LoadingDots';
import MarkdownContent from '@/utils/markdown';

const InterviewReport: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<InterviewReportType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!sessionId) return;

    const fetchReport = async () => {
      try {
        // Poll for report if it's not ready yet
        let retries = 0;
        while (retries < 10) {
          try {
            const data = await interviewApi.getReport(sessionId);
            setReport(data);
            setLoading(false);
            return;
          } catch {
            retries++;
            await new Promise((r) => setTimeout(r, 2000));
          }
        }
        throw new Error('报告生成超时，请稍后重试');
      } catch (e: unknown) {
        const err = e as { message?: string };
        setError(err.message || '获取报告失败');
        setLoading(false);
      }
    };

    fetchReport();
  }, [sessionId]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <LoadingDots text="正在加载复盘报告" className="justify-center mb-4" />
        <p className="text-sm text-slate-400">报告正在生成中，请稍候...</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6">
          <p className="text-red-600 mb-4">{error || '报告未找到'}</p>
          <button
            onClick={() => navigate('/history/interview')}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm transition-colors"
          >
            返回历史记录
          </button>
        </div>
      </div>
    );
  }

  const { overallScore, dimensions, overallComment, roundReviews, highlights, weaknesses, suggestions } = report;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6 pb-16">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/history/interview')}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          返回历史记录
        </button>
      </div>

      {/* Title */}
      <div className="text-center">
        <h1 className="text-2xl font-bold text-slate-800">模拟面试复盘报告</h1>
      </div>

      {/* Overall Score */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 text-center">
        <p className="text-sm text-slate-500 mb-3">总体评分</p>
        <div className="text-5xl font-bold text-primary-600 mb-2">{overallScore}</div>
        <p className="text-sm text-slate-400">/ 100</p>
        <div className="w-48 h-3 bg-slate-100 rounded-full overflow-hidden mx-auto mt-3">
          <div
            className={`h-full rounded-full transition-all duration-1000 ${
              overallScore >= 80 ? 'bg-green-500' : overallScore >= 60 ? 'bg-yellow-500' : 'bg-red-500'
            }`}
            style={{ width: `${overallScore}%` }}
          />
        </div>
        <p className="text-sm text-slate-500 mt-2">
          {overallScore >= 85 ? '优秀' : overallScore >= 70 ? '良好' : overallScore >= 60 ? '一般' : '需加强'}
        </p>
      </div>

      {/* Dimension Scores */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary-500" />
            各维度评分
          </h3>
          <ScoreBar label="技术深度" score={dimensions.techDepth} />
          <ScoreBar label="表达清晰度" score={dimensions.clarity} />
          <ScoreBar label="逻辑性" score={dimensions.logic} />
          <ScoreBar label="岗位匹配度" score={dimensions.jobMatch} />
        </div>
        <RadarChartView scores={dimensions} />
      </div>

      {/* Overall Comment */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-3">
          <MessageSquare className="w-5 h-5 text-primary-500" />
          整体评价
        </h3>
        <MarkdownContent content={overallComment} />
      </div>

      {/* Round Reviews */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 mb-4">各轮回顾</h3>
        <div className="space-y-4">
          {roundReviews.map((review) => (
            <div
              key={review.round}
              className="p-4 rounded-xl bg-slate-50 border border-slate-100"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-flex items-center justify-center w-6 h-6 bg-primary-100 text-primary-700 rounded-full text-xs font-semibold">
                  {review.round}
                </span>
                <span className="text-sm font-medium text-slate-700">第 {review.round} 轮</span>
              </div>
              <p className="text-sm text-slate-500 mb-2">
                <strong className="text-slate-600">问题：</strong>
                {review.question.length > 100
                  ? review.question.slice(0, 100) + '...'
                  : review.question}
              </p>
              {review.answerSummary && (
                <p className="text-sm text-slate-500 mb-2">
                  <strong className="text-slate-600">回答摘要：</strong>
                  {review.answerSummary}
                </p>
              )}
              <p className="text-sm text-slate-500">
                <strong className="text-slate-600">点评：</strong>
                {review.comment}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Highlights */}
      {highlights.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-4">
            <Star className="w-5 h-5 text-yellow-500" />
            优秀回答摘录
          </h3>
          <div className="space-y-3">
            {highlights.map((h, i) => (
              <div
                key={i}
                className="p-4 rounded-xl bg-yellow-50 border border-yellow-100 flex items-start gap-3"
              >
                <Star className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                <div>
                  <span className="text-xs font-medium text-yellow-600">第 {h.round} 轮</span>
                  <p className="text-sm text-slate-600 mt-1">{h.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weaknesses */}
      {weaknesses.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-4">
            <AlertTriangle className="w-5 h-5 text-orange-500" />
            待加强方向
          </h3>
          <ul className="space-y-2">
            {weaknesses.map((w, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                <span className="text-orange-400 mt-0.5">⚠</span>
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-4">
            <Lightbulb className="w-5 h-5 text-green-500" />
            改进建议
          </h3>
          <ul className="space-y-2">
            {suggestions.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                <span className="text-green-500 mt-0.5">✓</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-center gap-3 pt-4">
        <button
          onClick={() => navigate('/interview')}
          className="px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-xl transition-colors"
        >
          再来一次面试
        </button>
        <button
          onClick={() => navigate('/')}
          className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-xl transition-colors"
        >
          返回首页
        </button>
      </div>
    </div>
  );
};

export default InterviewReport;
