import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, Briefcase } from 'lucide-react';

const HistoryOverview: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回首页
      </button>

      <h1 className="text-2xl font-bold text-slate-800 mb-2">历史记录</h1>
      <p className="text-slate-500 text-sm mb-8">查看你的刷题和模拟面试历史记录</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Practice History */}
        <button
          onClick={() => navigate('/history/practice')}
          className="bg-white rounded-2xl border-2 border-slate-200 hover:border-blue-300 shadow-sm p-6 text-left transition-all duration-200 hover:shadow-md group"
        >
          <div className="inline-flex p-3 rounded-xl bg-blue-100 mb-4 group-hover:bg-blue-200 transition-colors">
            <BookOpen className="w-6 h-6 text-blue-600" />
          </div>
          <h3 className="text-lg font-semibold text-slate-800 mb-1">刷题记录</h3>
          <p className="text-sm text-slate-500">
            查看所有刷题历史、正确率和薄弱主题分析
          </p>
        </button>

        {/* Interview History */}
        <button
          onClick={() => navigate('/history/interview')}
          className="bg-white rounded-2xl border-2 border-slate-200 hover:border-purple-300 shadow-sm p-6 text-left transition-all duration-200 hover:shadow-md group"
        >
          <div className="inline-flex p-3 rounded-xl bg-purple-100 mb-4 group-hover:bg-purple-200 transition-colors">
            <Briefcase className="w-6 h-6 text-purple-600" />
          </div>
          <h3 className="text-lg font-semibold text-slate-800 mb-1">面试记录</h3>
          <p className="text-sm text-slate-500">
            查看模拟面试历史及复盘报告
          </p>
        </button>
      </div>
    </div>
  );
};

export default HistoryOverview;
