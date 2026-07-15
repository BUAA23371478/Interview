import React, { useState } from 'react';
import ModeCard from '@/components/ModeCard';
import api from '@/api/client';

const HomePage: React.FC = () => {
  const [testResult, setTestResult] = useState<{
    loading: boolean;
    chatOk?: boolean;
    chatModel?: string;
    chatLatency?: number;
    chatError?: string;
    embOk?: boolean;
    embModel?: string;
    embDim?: number;
    embError?: string;
  } | null>(null);

  const handleTestConnection = async () => {
    setTestResult({ loading: true });
    // 并行测试 Chat API 和 Embedding API
    const [chatRes, embRes] = await Promise.allSettled([
      api.get<{ ok: boolean; model: string; latency_ms: number; error?: string }>('/llm/test'),
      api.get<{ ok: boolean; model: string; dimension: number; error?: string }>('/embedding/test'),
    ]);

    const chat = chatRes.status === 'fulfilled' ? chatRes.value : null;
    const emb = embRes.status === 'fulfilled' ? embRes.value : null;

    setTestResult({
      loading: false,
      chatOk: chat?.ok ?? false,
      chatModel: chat?.model ?? 'N/A',
      chatLatency: chat?.latency_ms ?? 0,
      chatError: chat?.error ?? (chatRes.status === 'rejected' ? '请求失败' : undefined),
      embOk: emb?.ok ?? false,
      embModel: emb?.model ?? 'N/A',
      embDim: emb?.dimension ?? 0,
      embError: emb?.error ?? (embRes.status === 'rejected' ? '请求失败' : undefined),
    });
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 sm:py-16">
      {/* Hero */}
      <div className="text-center mb-10 sm:mb-14">
        <h1 className="text-3xl sm:text-4xl font-bold text-slate-800 mb-4">
          AI 智能刷题与模拟面试
        </h1>
        <p className="text-slate-500 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed">
          专注技术面试备考，提供<strong className="text-slate-700">刷题练习</strong>
          与<strong className="text-slate-700">模拟面试</strong>两种核心模式，
          让每一次练习都更有针对性
        </p>
      </div>

      {/* Mode Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl mx-auto">
        <ModeCard mode="practice" />
        <ModeCard mode="interview" />
      </div>

      {/* Knowledge Base Card */}
      <div className="mt-6 max-w-2xl mx-auto">
        <div
          onClick={() => window.location.hash = '#/knowledge'}
          className="group cursor-pointer bg-white rounded-2xl border border-slate-200 shadow-sm p-6 hover:border-amber-300 hover:shadow-md transition-all duration-200 flex items-center gap-5"
        >
          <div className="p-3 rounded-xl bg-amber-100 group-hover:bg-amber-200 transition-colors">
            <svg className="w-7 h-7 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-slate-800 group-hover:text-amber-700 transition-colors">
              📚 知识库管理
            </h3>
            <p className="text-sm text-slate-500 mt-1 leading-relaxed">
              上传技术文档构建 RAG 知识库，增强刷题出题和面试提问的针对性与准确性
            </p>
          </div>
          <div className="text-slate-300 group-hover:text-amber-500 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </div>
        </div>
      </div>

      {/* API Connectivity Test */}
      <div className="mt-12 max-w-md mx-auto">
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-700">🔗 API 连通性测试</h3>
              <p className="text-xs text-slate-400 mt-0.5">Chat + Embedding 双 API 连接状态</p>
            </div>
            <button
              onClick={handleTestConnection}
              disabled={testResult?.loading}
              className="px-4 py-2 text-sm font-medium bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-700 rounded-lg transition-colors"
            >
              {testResult?.loading ? '测试中...' : '开始测试'}
            </button>
          </div>

          {testResult && !testResult.loading && (
            <div className="mt-3 space-y-2">
              {/* Chat API */}
              <div className={`p-3 rounded-lg text-sm ${
                testResult.chatOk
                  ? 'bg-green-50 border border-green-200 text-green-700'
                  : 'bg-red-50 border border-red-200 text-red-600'
              }`}>
                {testResult.chatOk ? (
                  <span>💬 Chat API ✅ — {testResult.chatModel}，{testResult.chatLatency}ms</span>
                ) : (
                  <span>💬 Chat API ❌ — {testResult.chatError || '连接失败'}</span>
                )}
              </div>
              {/* Embedding API */}
              <div className={`p-3 rounded-lg text-sm ${
                testResult.embOk
                  ? 'bg-green-50 border border-green-200 text-green-700'
                  : 'bg-red-50 border border-red-200 text-red-600'
              }`}>
                {testResult.embOk ? (
                  <span>🧬 Embedding API ✅ — {testResult.embModel}，{testResult.embDim}维</span>
                ) : (
                  <span>🧬 Embedding API ❌ — {testResult.embError || '未配置或连接失败'}</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Features */}
      <div className="mt-16 grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl mx-auto">
        {[
          {
            emoji: '🤖',
            title: 'AI 驱动',
            desc: '智能生成题目与面试问题，根据表现动态调整难度',
          },
          {
            emoji: '📊',
            title: '深度复盘',
            desc: '多维度评分与个性化改进建议，精准定位薄弱环节',
          },
          {
            emoji: '💾',
            title: '历史追踪',
            desc: '自动记录每次练习，可视化成长轨迹与薄弱主题',
          },
        ].map((feature) => (
          <div
            key={feature.title}
            className="text-center p-5 rounded-2xl bg-white/60 border border-slate-100"
          >
            <div className="text-3xl mb-3">{feature.emoji}</div>
            <h3 className="font-semibold text-slate-800 mb-1">{feature.title}</h3>
            <p className="text-sm text-slate-500 leading-relaxed">{feature.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default HomePage;
