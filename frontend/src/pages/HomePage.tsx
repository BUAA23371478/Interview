import React, { useState } from 'react';
import ModeCard from '@/components/ModeCard';
import api from '@/api/client';

const HomePage: React.FC = () => {
  const [testResult, setTestResult] = useState<{
    loading: boolean;
    ok?: boolean;
    model?: string;
    latency?: number;
    error?: string;
  } | null>(null);

  const handleTestConnection = async () => {
    setTestResult({ loading: true });
    try {
      const res = await api.get<{
        ok: boolean;
        model: string;
        latency_ms: number;
        error?: string;
      }>('/llm/test');
      setTestResult({
        loading: false,
        ok: res.ok,
        model: res.model,
        latency: res.latency_ms,
        error: res.error,
      });
    } catch (e: unknown) {
      setTestResult({
        loading: false,
        ok: false,
        error: '请求失败，请检查后端服务是否启动',
      });
    }
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

      {/* API Connectivity Test */}
      <div className="mt-12 max-w-md mx-auto">
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-700">🔗 API 连通性测试</h3>
              <p className="text-xs text-slate-400 mt-0.5">测试后端与大模型的连接状态</p>
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
            <div className={`mt-3 p-3 rounded-lg text-sm ${
              testResult.ok
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-600'
            }`}>
              {testResult.ok ? (
                <>
                  <span className="font-medium">✅ 连接成功</span>
                  <span className="ml-2 text-green-600">
                    模型 {testResult.model}，耗时 {testResult.latency}ms
                  </span>
                </>
              ) : (
                <>
                  <span className="font-medium">❌ 连接失败</span>
                  {testResult.error && (
                    <span className="ml-2">{testResult.error}</span>
                  )}
                </>
              )}
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
