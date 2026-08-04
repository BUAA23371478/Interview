import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { practiceApi, PracticeAnswerResp } from '../api/practice'

export default function PracticeSession() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [phase, setPhase] = useState<'answering' | 'thinking' | 'feedback'>('answering')
  const [feedback, setFeedback] = useState<PracticeAnswerResp | null>(null)
  const [index, setIndex] = useState(0)
  const [total, setTotal] = useState(0)
  const [difficulty, setDifficulty] = useState('medium')
  const [error, setError] = useState('')

  // 挂载时加载当前题目（setup 页 start 返回 session_id 后跳转过来）
  useEffect(() => {
    if (!sessionId) {
      setError('缺少会话 ID')
      return
    }
    practiceApi
      .current(sessionId)
      .then((r) => {
        if (r.finished) {
          // 会话已结束，跳回首页
          navigate('/')
          return
        }
        setQuestion(r.question)
        setIndex(r.question_index)
        setTotal(r.total_rounds)
        setDifficulty(r.difficulty)
      })
      .catch((e) => setError((e as Error).message))
  }, [sessionId, navigate])

  const submit = async () => {
    if (!sessionId || !answer.trim()) return
    const text = answer.trim()
    setAnswer('')
    setPhase('thinking')
    setError('')
    try {
      const r = await practiceApi.answer(sessionId, text)
      if (r.finished) {
        navigate(`/profile`)
        return
      }
      setFeedback(r)
      setQuestion(r.question)
      setIndex(r.question_index)
      setTotal(r.total_rounds)
      setDifficulty(r.difficulty)
      setPhase('feedback')
    } catch (e) {
      setError((e as Error).message)
      setPhase('answering')
    }
  }

  const next = () => setPhase('answering')

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="card p-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-800">专项练习</h2>
          <p className="text-sm text-gray-500">第 {Math.min(index + 1, total || 1)} / {total || '…'} 题</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${difficulty === 'hard' ? 'bg-red-100 text-red-600' : difficulty === 'easy' ? 'bg-green-100 text-green-600' : 'bg-yellow-100 text-yellow-700'}`}>
          {{ easy: '简单', medium: '中等', hard: '困难' }[difficulty] || difficulty}
        </span>
      </div>

      <div className="card p-6">
        <div className="text-lg font-medium text-gray-800 mb-4">{question || '正在加载题目…'}</div>
        {phase === 'feedback' && feedback && (
          <div className="space-y-4">
            <div className="flex items-center space-x-3">
              <span className="text-3xl font-bold text-purple-600">{feedback.score}</span>
              <span className="text-gray-500">/ 10 分</span>
              {feedback.is_correct ? (
                <span className="badge-easy px-2 py-1 rounded-full text-xs font-semibold">回答正确</span>
              ) : (
                <span className="badge-hard px-2 py-1 rounded-full text-xs font-semibold">需要加强</span>
              )}
            </div>
            <div className="text-sm text-gray-600 bg-gray-50 rounded-xl p-4">{feedback.feedback}</div>
            {feedback.reference && (
              <div className="text-sm">
                <div className="font-semibold text-gray-700 mb-1">💯 参考答案</div>
                <div className="text-gray-600 whitespace-pre-wrap">{feedback.reference}</div>
              </div>
            )}
            <button className="btn-primary" onClick={next}>下一题</button>
          </div>
        )}
        {phase === 'thinking' && <div className="text-sm text-gray-500">正在评分…</div>}
      </div>

      {error && <div className="text-sm text-red-500">{error}</div>}

      {phase !== 'feedback' && (
        <div className="card p-5">
          <div className="text-sm font-semibold text-gray-700 mb-2">✍️ 你的回答</div>
          <textarea
            className="input-field w-full min-h-[220px] resize-y leading-relaxed"
            placeholder="输入你的回答，尽量展开：思路、要点、示例…（可长按拖动调整高度）"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={phase !== 'answering'}
          />
          <div className="flex justify-end mt-3">
            <button className="btn-primary" onClick={submit} disabled={phase !== 'answering'}>提交回答</button>
          </div>
        </div>
      )}
    </div>
  )
}
