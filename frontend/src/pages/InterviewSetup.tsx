import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { interviewApi } from '../api/interview'

export default function InterviewSetup() {
  const navigate = useNavigate()
  const [jd, setJd] = useState('')
  const [resume, setResume] = useState('')
  const [rounds, setRounds] = useState(10)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const start = async () => {
    if (!jd.trim()) {
      setError('请填写岗位描述 JD')
      return
    }
    setLoading(true)
    setError('')
    try {
      const r = await interviewApi.start({ jd_text: jd, resume_text: resume, total_rounds: rounds })
      navigate(`/interview/session/${r.session_id}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">AI 模拟面试</h2>
        <p className="text-sm text-gray-500">填写岗位描述（JD）与简历，AI 将为你定制一场完整面试。</p>
      </div>
      <div className="card p-6 space-y-4">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">岗位描述 JD *</label>
          <textarea
            className="input-field min-h-[140px]"
            placeholder="粘贴岗位描述，例如：招聘 AI Agent 工程师，3 年经验，熟悉 RAG/LangChain/MCP…"
            value={jd}
            onChange={(e) => setJd(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">简历（可选）</label>
          <textarea
            className="input-field min-h-[120px]"
            placeholder="粘贴简历文本，帮助 AI 针对你的优劣势出题"
            value={resume}
            onChange={(e) => setResume(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">题目数量</label>
          <select className="input-field" value={rounds} onChange={(e) => setRounds(Number(e.target.value))}>
            {[5, 8, 10, 15, 20].map((n) => (
              <option key={n} value={n}>{n} 题</option>
            ))}
          </select>
        </div>
        {error && <div className="text-sm text-red-500">{error}</div>}
        <button className="btn-primary w-full" onClick={start} disabled={loading}>
          {loading ? '准备中…' : '开始面试'}
        </button>
      </div>
    </div>
  )
}
