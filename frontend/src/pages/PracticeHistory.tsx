import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ChevronRight, AlertTriangle, Trash2 } from 'lucide-react';
import { practiceApi } from '@/api/practice';
import type { PracticeSessionSummary, PracticeStats } from '@/types/practice';
import { formatDate, formatAccuracy } from '@/utils/format';
import LoadingDots from '@/components/LoadingDots';

const PracticeHistory: React.FC = () => {
  const navigate = useNavigate();
  const [records, setRecords] = useState<PracticeSessionSummary[]>([]);
  const [stats, setStats] = useState<PracticeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [historyData, statsData] = await Promise.all([
        practiceApi.getHistory(1, 50),
        practiceApi.getStats().catch(() => null),
      ]);
      setRecords(historyData.records || []);
      setStats(statsData);
    } catch {
      setError('加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm('确定删除这条刷题记录吗？')) return;
    setDeleting(sessionId);
    try {
      await practiceApi.deleteSession(sessionId);
      setRecords((prev) => prev.filter((r) => r.sessionId !== sessionId));
    } catch {
      alert('删除失败，请重试');
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <LoadingDots text="加载历史记录" className="justify-center" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate('/history')}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回历史记录
      </button>

      <h1 className="text-2xl font-bold text-slate-800 mb-2">刷题历史记录</h1>
      <p className="text-slate-500 text-sm mb-8">记录每次刷题的主题、正确率和薄弱环节</p>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          {[
            { label: '总题数', value: stats.totalQuestions },
            { label: '正确数', value: stats.totalCorrect },
            { label: '正确率', value: formatAccuracy(stats.overallAccuracy) },
            { label: '薄弱主题', value: stats.weakTopics.length },
          ].map((s) => (
            <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-4 text-center">
              <div className="text-2xl font-bold text-primary-600">{s.value}</div>
              <div className="text-xs text-slate-400 mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-600 mb-6">{error}</div>
      )}

      {records.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-400">暂无刷题记录</p>
          <button
            onClick={() => navigate('/practice')}
            className="mt-4 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-xl text-sm transition-colors"
          >
            开始刷题
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((record) => (
            <div
              key={record.sessionId}
              className="w-full bg-white rounded-xl border border-slate-200 hover:border-primary-300 shadow-sm p-4 flex items-center justify-between transition-all duration-200 hover:shadow-md"
            >
              <button
                onClick={() => navigate(`/history/practice/${record.sessionId}`)}
                className="flex-1 flex items-center justify-between text-left min-w-0"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium text-slate-800 truncate">{record.topic}</h3>
                    {record.accuracy < 60 && (
                      <span title="薄弱主题"><AlertTriangle className="w-4 h-4 text-orange-500 flex-shrink-0" /></span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span>{formatDate(record.createdAt)}</span>
                    <span>{record.totalQuestions} 题</span>
                    <span className={`font-medium ${
                      record.accuracy >= 80 ? 'text-green-500' :
                      record.accuracy >= 60 ? 'text-yellow-500' : 'text-red-500'
                    }`}>
                      正确率 {formatAccuracy(record.accuracy)}
                    </span>
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-300 flex-shrink-0 ml-3" />
              </button>
              <button
                onClick={(e) => handleDelete(e, record.sessionId)}
                disabled={deleting === record.sessionId}
                className="ml-2 p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors flex-shrink-0"
                title="删除记录"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {stats && stats.weakTopics.length > 0 && (
        <div className="mt-8 bg-orange-50 rounded-2xl border border-orange-200 p-6">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-3">
            <AlertTriangle className="w-5 h-5 text-orange-500" />
            薄弱主题（正确率 &lt; 60%）
          </h3>
          <div className="space-y-2">
            {stats.weakTopics.map((wt) => (
              <div key={wt.topic} className="flex items-center justify-between text-sm">
                <span className="text-slate-700">{wt.topic}</span>
                <span className="text-orange-600 font-medium">
                  {wt.accuracy}% · {wt.totalQuestions} 题
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default PracticeHistory;
