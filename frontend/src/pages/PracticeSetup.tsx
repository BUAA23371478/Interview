import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Sparkles } from 'lucide-react';
import { practiceApi } from '@/api/practice';

const PracticeSetup: React.FC = () => {
  const [topic, setTopic] = useState('');
  const [maxQuestions, setMaxQuestions] = useState(20);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleStart = async () => {
    setError('');

    if (!topic.trim()) {
      setError('请输入练习主题');
      return;
    }

    if (topic.length > 50) {
      setError('主题请控制在50字以内');
      return;
    }

    setLoading(true);
    try {
      const res = await practiceApi.start(topic.trim(), maxQuestions);
      navigate(`/practice/${res.sessionId}`, {
        state: { topic: topic.trim() },
      });
    } catch (e: unknown) {
      const err = e as { message?: string };
      setError(err.message || '请输入技术面试相关主题');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回首页
      </button>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-8">
        <div className="text-center mb-8">
          <div className="inline-flex p-3 rounded-xl bg-blue-100 mb-4">
            <Sparkles className="w-7 h-7 text-blue-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-800 mb-2">选择刷题主题</h1>
          <p className="text-slate-500 text-sm">
            输入你想要练习的技术方向，AI 将围绕该主题持续出题
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              练习主题
            </label>
            <input
              type="text"
              value={topic}
              onChange={(e) => {
                setTopic(e.target.value);
                setError('');
              }}
              onKeyDown={(e) => e.key === 'Enter' && handleStart()}
              placeholder="例如：Java 后端开发、MySQL 优化、Redis 缓存"
              maxLength={50}
              disabled={loading}
              className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all disabled:opacity-50"
            />
            <div className="flex items-center justify-between mt-1.5">
              <p className="text-xs text-slate-400">
                支持任意技术面试相关主题
              </p>
              <span className={`text-xs ${topic.length > 50 ? 'text-red-500' : 'text-slate-400'}`}>
                {topic.length}/50
              </span>
            </div>
          </div>

          {/* Max Questions */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              题目数量上限
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={3}
                max={50}
                value={maxQuestions}
                onChange={(e) => setMaxQuestions(Number(e.target.value))}
                disabled={loading}
                className="flex-1 accent-blue-600"
              />
              <span className="w-12 text-center font-semibold text-lg text-slate-700">
                {maxQuestions}
              </span>
              <span className="text-sm text-slate-400">题</span>
            </div>
            <p className="text-xs text-slate-400 mt-1">达到上限后自动结束，可在历史记录中查看</p>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-600">
              {error}
            </div>
          )}

          <button
            onClick={handleStart}
            disabled={loading || !topic.trim()}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all duration-200 active:scale-95 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0s' }} />
                  <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.2s' }} />
                  <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.4s' }} />
                </span>
                校验主题中...
              </>
            ) : (
              '开始刷题'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default PracticeSetup;
