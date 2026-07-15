import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, XCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { practiceApi } from '@/api/practice';
import type { PracticeSessionDetail } from '@/types/practice';
import { formatDate } from '@/utils/format';
import MarkdownContent from '@/utils/markdown';
import LoadingDots from '@/components/LoadingDots';

const PracticeDetail: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<PracticeSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    (async () => {
      if (!sessionId) return;
      try {
        const data = await practiceApi.getSessionDetail(sessionId);
        setDetail(data);
        const pending = data.records.find((r) => !r.userAnswer);
        if (pending) setExpanded(new Set([pending.id]));
      } catch {
        setError('加载失败');
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // 必须在所有条件 return 之前调用（React hooks 规则）
  const records = detail?.records ?? [];
  const lastPendingIdx = useMemo(() => {
    for (let i = records.length - 1; i >= 0; i--) {
      if (!records[i].userAnswer) return i;
    }
    return -1;
  }, [records]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <LoadingDots text="加载会话详情" className="justify-center" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 text-center">
        <p className="text-slate-500">{error || '会话不存在'}</p>
        <button onClick={() => navigate('/history/practice')} className="mt-4 text-primary-600 hover:underline text-sm">
          返回刷题历史
        </button>
      </div>
    );
  }

  const { session } = detail;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate('/history/practice')}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回刷题历史
      </button>

      {/* Header */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800 mb-2">{session.topic}</h1>
            <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
              <span>{formatDate(session.createdAt)}</span>
              <span className="font-medium text-slate-600">
                {session.totalQuestions}/{session.maxQuestions || 20} 题已答
              </span>
              <span
                className={`px-1.5 py-0.5 rounded-full text-xs ${
                  session.status === 'completed'
                    ? 'bg-green-100 text-green-600'
                    : 'bg-blue-100 text-blue-600'
                }`}
              >
                {session.status === 'completed' ? '已完成' : '进行中'}
              </span>
            </div>
          </div>
          {session.status !== 'completed' && (
            <button
              onClick={() =>
                navigate(`/practice/${session.id}`, { state: { topic: session.topic } })
              }
              className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-xl transition-colors flex-shrink-0"
            >
              继续练习
            </button>
          )}
        </div>
      </div>

      {/* Questions */}
      {records.length === 0 ? (
        <div className="text-center py-12 text-slate-400">暂无题目</div>
      ) : (
        <div className="space-y-3">
          {records.map((record, idx) => {
            const isPending = !record.userAnswer && idx === lastPendingIdx;
            const isSkipped = record.userAnswer === '不了解';
            const isOpen = expanded.has(record.id);

            return (
              <div
                key={record.id}
                className={`bg-white rounded-2xl border shadow-sm overflow-hidden transition-all ${
                  isPending
                    ? 'border-primary-400 ring-1 ring-primary-100'
                    : 'border-slate-200'
                }`}
              >
                {/* Summary Row */}
                <button
                  onClick={() => toggleExpand(record.id)}
                  className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-semibold text-slate-700 text-sm">
                      第 {record.questionNumber} 题
                    </span>
                    {isPending ? (
                      <span className="px-2 py-0.5 text-xs bg-primary-100 text-primary-700 rounded-full font-medium">
                        待回答
                      </span>
                    ) : isSkipped ? (
                      <span className="px-2 py-0.5 text-xs bg-orange-100 text-orange-600 rounded-full font-medium">
                        不了解
                      </span>
                    ) : record.isCorrect ? (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <CheckCircle className="w-3.5 h-3.5" /> 正确
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-red-500">
                        <XCircle className="w-3.5 h-3.5" /> {record.score}分
                      </span>
                    )}
                    <span className="text-xs text-slate-400 truncate max-w-[300px] hidden sm:inline">
                      {record.question.slice(0, 80)}...
                    </span>
                  </div>
                  {isOpen ? (
                    <ChevronDown className="w-5 h-5 text-slate-400 flex-shrink-0" />
                  ) : (
                    <ChevronRight className="w-5 h-5 text-slate-400 flex-shrink-0" />
                  )}
                </button>

                {/* Expanded Detail */}
                {isOpen && (
                  <div className="px-5 pb-5 border-t border-slate-100 space-y-3 pt-4">
                    {/* Question */}
                    <div className="p-3 bg-slate-50 rounded-xl">
                      <p className="text-xs text-slate-400 mb-1">📋 题目</p>
                      <div className="text-sm text-slate-700">
                        <MarkdownContent content={record.question} />
                      </div>
                    </div>

                    {/* Pending → 提示用户用顶部"继续练习" */}
                    {isPending ? (
                      <div className="p-4 bg-primary-50 rounded-xl text-center">
                        <p className="text-sm text-primary-700">
                          这道题还未回答，点击上方「继续练习」进入答题
                        </p>
                      </div>
                    ) : (
                      <>
                        {/* User Answer */}
                        <div className="p-3 bg-blue-50 rounded-xl">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="text-xs text-slate-400">📝 你的答案</p>
                            {isSkipped && (
                              <span className="px-1.5 py-0.5 text-xs bg-orange-100 text-orange-600 rounded-full">
                                不了解
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-slate-700 whitespace-pre-wrap">
                            {isSkipped ? '（选择查看参考答案）' : record.userAnswer}
                          </div>
                        </div>

                        {/* Reference Answer */}
                        <div className="p-3 bg-green-50 rounded-xl">
                          <p className="text-xs text-slate-400 mb-1">📖 参考答案</p>
                          <div className="text-sm text-slate-700">
                            <MarkdownContent
                              content={record.feedback || record.referenceAnswer}
                            />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PracticeDetail;
