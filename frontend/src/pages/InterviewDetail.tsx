import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, MessageSquare, Star, AlertTriangle, Lightbulb } from 'lucide-react';
import { interviewApi } from '@/api/interview';
import type { InterviewSessionDetail } from '@/types/interview';
import { formatDate } from '@/utils/format';
import LoadingDots from '@/components/LoadingDots';
import ScoreBar from '@/components/ScoreBar';
import RadarChartView from '@/components/RadarChart';
import MarkdownContent from '@/utils/markdown';

const InterviewDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<InterviewSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    const fetch = async () => {
      try {
        const data = await interviewApi.getSessionDetail(id);
        setDetail(data);
      } catch {
        setError('加载详情失败');
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <LoadingDots text="加载面试详情" className="justify-center" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6">
          <p className="text-red-600">{error || '未找到面试记录'}</p>
        </div>
      </div>
    );
  }

  const { session, qaRecords, report } = detail;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6 pb-16">
      <button
        onClick={() => navigate('/history/interview')}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回面试记录
      </button>

      <h1 className="text-2xl font-bold text-slate-800">面试详情</h1>

      {/* Session Info */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-slate-400">日期</span>
            <p className="font-medium text-slate-700">{formatDate(session.createdAt)}</p>
          </div>
          <div>
            <span className="text-slate-400">轮数</span>
            <p className="font-medium text-slate-700">{session.completedRounds}/{session.totalRounds}</p>
          </div>
          <div>
            <span className="text-slate-400">状态</span>
            <p className={`font-medium ${session.status === 'completed' ? 'text-green-600' : 'text-yellow-600'}`}>
              {session.status === 'completed' ? '已完成' : '进行中'}
            </p>
          </div>
          <div>
            <span className="text-slate-400">总评分</span>
            <p className="font-medium text-slate-700">
              {session.overallScore != null ? `${session.overallScore}/100` : '未评分'}
            </p>
          </div>
        </div>
      </div>

      {/* QA Records */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-4">
          <MessageSquare className="w-5 h-5 text-primary-500" />
          问答记录
        </h3>
        <div className="space-y-4">
          {qaRecords.map((qa) => (
            <div key={qa.id} className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-medium text-slate-400">
                  第 {qa.roundNumber} 轮{qa.isFollowUp ? ' · 追问' : ''}
                </span>
              </div>
              <p className="text-sm text-slate-700 mb-2">
                <strong className="text-purple-600">Q: </strong>
                {qa.question}
              </p>
              {qa.userAnswer && (
                <p className="text-sm text-slate-600 mb-2">
                  <strong className="text-blue-600">A: </strong>
                  {qa.userAnswer.length > 200 ? qa.userAnswer.slice(0, 200) + '...' : qa.userAnswer}
                </p>
              )}
              {qa.aiFeedback && (
                <p className="text-sm text-slate-500 italic">
                  💬 {qa.aiFeedback}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Report (if exists) */}
      {report && (
        <>
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 text-center">
            <div className="text-5xl font-bold text-primary-600">{report.overallScore}</div>
            <p className="text-sm text-slate-400 mt-1">总体评分 / 100</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-3">
              <h3 className="font-semibold text-slate-800 mb-2">各维度评分</h3>
              <ScoreBar label="技术深度" score={report.dimensions.techDepth} />
              <ScoreBar label="表达清晰度" score={report.dimensions.clarity} />
              <ScoreBar label="逻辑性" score={report.dimensions.logic} />
              <ScoreBar label="岗位匹配度" score={report.dimensions.jobMatch} />
            </div>
            <RadarChartView scores={report.dimensions} />
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
            <h3 className="font-semibold text-slate-800 mb-3">整体评价</h3>
            <MarkdownContent content={report.overallComment} />
          </div>

          {report.highlights.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-3">
                <Star className="w-5 h-5 text-yellow-500" />
                优秀回答摘录
              </h3>
              {report.highlights.map((h, i) => (
                <div key={i} className="p-3 rounded-xl bg-yellow-50 border border-yellow-100 mb-2">
                  <span className="text-xs font-medium text-yellow-600">第 {h.round} 轮</span>
                  <p className="text-sm text-slate-600 mt-1">{h.reason}</p>
                </div>
              ))}
            </div>
          )}

          {report.weaknesses.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-3">
                <AlertTriangle className="w-5 h-5 text-orange-500" />
                待加强方向
              </h3>
              <ul className="space-y-2">
                {report.weaknesses.map((w, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                    <span className="text-orange-400">⚠</span> {w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.suggestions.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-3">
                <Lightbulb className="w-5 h-5 text-green-500" />
                改进建议
              </h3>
              <ul className="space-y-2">
                {report.suggestions.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                    <span className="text-green-500">✓</span> {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default InterviewDetail;
