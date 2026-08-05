import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { practiceApi } from '../api/practice'

const STYLES = ['通用', '字节', '阿里', '腾讯', '美团']

export default function PracticeSetup() {
  const navigate = useNavigate()
  const [topic, setTopic] = useState('Redis')
  const [difficulty, setDifficulty] = useState('medium')
  const [style, setStyle] = useState('通用')
  const [rounds, setRounds] = useState(10)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const start = async () => {
    if (!topic.trim()) {
      setError('请填写练习主题')
      return
    }
    setLoading(true)
    setError('')
    try {
      const r = await practiceApi.start({
        topic: topic.trim(),
        difficulty,
        company_style: style,
        total_rounds: rounds,
      })
      navigate(`/practice/session/${r.session_id}`, { state: { ragHit: r.rag_hit, topic: topic.trim() } })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">专项练习</h2>
        <p className="text-sm text-gray-500">按主题、难度与公司风格刷题，逐题评分并沉淀错题本。</p>
      </div>
      <div className="card p-6 space-y-4">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">练习主题</label>
          <input
            className="input-field"
            placeholder="例如：Redis / Java 并发 / 系统设计"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">难度</label>
          <div className="flex space-x-2">
            {['easy', 'medium', 'hard'].map((d) => (
              <button
                key={d}
                className={`px-4 py-2 rounded-lg text-sm border transition ${
                  difficulty === d ? 'bg-purple-100 border-purple-400 text-purple-700' : 'border-gray-200 text-gray-600'
                }`}
                onClick={() => setDifficulty(d)}
              >
                {{ easy: '简单', medium: '中等', hard: '困难' }[d]}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">公司风格</label>
          <div className="flex flex-wrap gap-2">
            {STYLES.map((s) => (
              <button
                key={s}
                className={`px-3 py-1 rounded-full text-sm border transition ${
                  style === s ? 'bg-purple-100 border-purple-400 text-purple-700' : 'border-gray-200 text-gray-600'
                }`}
                onClick={() => setStyle(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">题目数量</label>
          <select className="input-field" value={rounds} onChange={(e) => setRounds(Number(e.target.value))}>
            {[5, 10, 15, 20].map((n) => (
              <option key={n} value={n}>{n} 题</option>
            ))}
          </select>
        </div>
        {error && <div className="text-sm text-red-500">{error}</div>}
        <button className="btn-primary w-full" onClick={start} disabled={loading}>
          {loading ? '准备中…' : '开始练习'}
        </button>
      </div>
    </div>
  )
}
