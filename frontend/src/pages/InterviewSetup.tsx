import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Target } from 'lucide-react';
import { interviewApi } from '@/api/interview';

const InterviewSetup: React.FC = () => {
  const navigate = useNavigate();
  const [jd, setJd] = useState('');
  const [resume, setResume] = useState('');
  const [rounds, setRounds] = useState(10);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    setError('');

    if (!jd.trim()) {
      setError('请输入目标岗位 JD');
      return;
    }
    if (!resume.trim()) {
      setError('请输入个人简历');
      return;
    }
    if (rounds < 3 || rounds > 20) {
      setError('面试轮数建议在 3-20 轮之间');
      return;
    }

    setLoading(true);
    try {
      const res = await interviewApi.create({
        jd: jd.trim(),
        resume: resume.trim(),
        total_rounds: rounds,
      });
      navigate(`/interview/${res.sessionId}`);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setError(err.message || '创建面试会话失败');
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
          <div className="inline-flex p-3 rounded-xl bg-purple-100 mb-4">
            <Target className="w-7 h-7 text-purple-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-800 mb-2">模拟面试设置</h1>
          <p className="text-slate-500 text-sm">
            粘贴目标岗位 JD 和个人简历，AI 将模拟真实面试场景
          </p>
        </div>

        <div className="space-y-5">
          {/* JD Input */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              目标岗位 JD
              <span className="text-red-400 ml-1">*</span>
            </label>
            <textarea
              value={jd}
              onChange={(e) => {
                setJd(e.target.value.slice(0, 5000));
                setError('');
              }}
              placeholder="请粘贴目标岗位的职位描述（JD），如岗位职责、技术要求等..."
              rows={5}
              maxLength={5000}
              disabled={loading}
              className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none disabled:opacity-50 text-sm"
            />
            <p className="text-xs text-slate-400 mt-1">{jd.length}/5000</p>
          </div>

          {/* Resume Input */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              个人简历
              <span className="text-red-400 ml-1">*</span>
            </label>
            <textarea
              value={resume}
              onChange={(e) => {
                setResume(e.target.value.slice(0, 5000));
                setError('');
              }}
              placeholder="请粘贴你的个人简历，包括教育背景、项目经历、技能栈、工作经验等..."
              rows={5}
              maxLength={5000}
              disabled={loading}
              className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none disabled:opacity-50 text-sm"
            />
            <p className="text-xs text-slate-400 mt-1">{resume.length}/5000</p>
          </div>

          {/* Rounds Setting */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              面试轮数
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={3}
                max={20}
                value={rounds}
                onChange={(e) => setRounds(Number(e.target.value))}
                disabled={loading}
                className="flex-1 accent-purple-600"
              />
              <span className="w-12 text-center font-semibold text-lg text-slate-700">
                {rounds}
              </span>
              <span className="text-sm text-slate-400">轮</span>
            </div>
            <p className="text-xs text-slate-400 mt-1">建议范围 3-20 轮，默认 10 轮</p>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-600">
              {error}
            </div>
          )}

          <button
            onClick={handleStart}
            disabled={loading || !jd.trim() || !resume.trim()}
            className="w-full py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all duration-200 active:scale-95 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0s' }} />
                  <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.2s' }} />
                  <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse-dot" style={{ animationDelay: '0.4s' }} />
                </span>
                创建面试中...
              </>
            ) : (
              '开始模拟面试'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default InterviewSetup;
