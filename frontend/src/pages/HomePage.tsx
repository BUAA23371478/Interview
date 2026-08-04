import { useNavigate } from 'react-router-dom'

export default function HomePage() {
  const navigate = useNavigate()
  return (
    <div className="space-y-8">
      <div className="card p-8 text-center">
        <h2 className="text-3xl font-bold text-gray-800">准备技术面试？让 AI 陪你实战</h2>
        <p className="mt-3 text-gray-500">基于你的 JD 与简历生成个性化面试题，逐题评分、追问、复盘，一键进知识库查漏补缺。</p>
        <div className="mt-6 flex justify-center space-x-4">
          <button className="btn-primary" onClick={() => navigate('/interview/setup')}>开始模拟面试</button>
          <button className="btn-ghost" onClick={() => navigate('/practice/setup')}>专项练习</button>
          <button className="btn-ghost" onClick={() => navigate('/knowledge')}>浏览知识库</button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          {
            icon: '🎯',
            title: 'AI 模拟面试',
            desc: '上传 JD 与简历，AI 规划题库、多轮追问、动态难度调节，最后输出完整评估报告与 4 周复习计划。',
          },
          {
            icon: '📚',
            title: '知识库 RAG',
            desc: '内置 300+ 面试题与 14 家公司面经，支持上传自己的技术文档，混合检索 + 智能问答。',
          },
          {
            icon: '📝',
            title: '专项练习',
            desc: '按主题/难度/公司风格刷题，逐题评分、错题本沉淀，跨会话记住你的薄弱点。',
          },
        ].map((m) => (
          <div key={m.title} className="card p-6 hover:shadow-xl transition">
            <div className="text-3xl">{m.icon}</div>
            <h3 className="mt-3 text-lg font-bold text-gray-800">{m.title}</h3>
            <p className="mt-2 text-sm text-gray-500">{m.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
