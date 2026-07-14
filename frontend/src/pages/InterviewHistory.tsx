import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ChevronRight, Trash2 } from 'lucide-react';
import { interviewApi } from '@/api/interview';
import type { InterviewSessionSummary } from '@/types/interview';
import { formatDate, truncateText } from '@/utils/format';
import LoadingDots from '@/components/LoadingDots';

const InterviewHistory: React.FC = () => {
  const navigate = useNavigate();
  const [records, setRecords] = useState<InterviewSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const data = await interviewApi.getHistory(1, 50);
      setRecords(data.records || []);
    } catch {
      setError('加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm('确定删除这条面试记录吗？')) return;
    setDeleting(sessionId);
    try {
      await interviewApi.deleteSession(sessionId);
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
        <LoadingDots text="加载面试记录" className="justify-center" />
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

      <h1 className="text-2xl font-bold text-slate-800 mb-2">模拟面试记录</h1>
      <p className="text-slate-500 text-sm mb-8">查看模拟面试历史和复盘报告</p>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-600 mb-6">{error}</div>
      )}

      {records.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-400">暂无面试记录</p>
          <button
            onClick={() => navigate('/interview')}
            className="mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-sm transition-colors"
          >
            开始模拟面试
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((record) => (
            <div
              key={record.sessionId}
              className="w-full bg-white rounded-xl border border-slate-200 hover:border-purple-300 shadow-sm p-4 flex items-center justify-between transition-all duration-200 hover:shadow-md"
            >
              <button
                onClick={() => navigate(`/history/interview/${record.sessionId}`)}
                className="flex-1 flex items-center justify-between text-left min-w-0"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium text-slate-800 truncate">
                      {truncateText(record.jdContent, 60)}
                    </h3>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span>{formatDate(record.createdAt)}</span>
                    <span>{record.completedRounds}/{record.totalRounds} 轮</span>
                    {record.overallScore != null && (
                      <span className={`font-medium ${
                        record.overallScore >= 80 ? 'text-green-500' :
                        record.overallScore >= 60 ? 'text-yellow-500' : 'text-red-500'
                      }`}>
                        {record.overallScore} 分
                      </span>
                    )}
                    <span className={`px-1.5 py-0.5 rounded-full text-xs ${
                      record.status === 'completed' ? 'bg-green-100 text-green-600' : 'bg-yellow-100 text-yellow-600'
                    }`}>
                      {record.status === 'completed' ? '已完成' : '进行中'}
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
    </div>
  );
};

export default InterviewHistory;
