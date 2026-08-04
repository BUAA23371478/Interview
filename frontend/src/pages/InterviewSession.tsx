import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { interviewApi, InterviewAnswerResp } from '../api/interview'

interface Msg {
  id: string
  role: 'interviewer' | 'user' | 'system'
  content: string
}

const DIFF_COLOR: Record<string, string> = {
  easy: 'badge-easy',
  medium: 'badge-medium',
  hard: 'badge-hard',
}

export default function InterviewSession() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Msg[]>([])
  const [answer, setAnswer] = useState('')
  const [phase, setPhase] = useState<'answering' | 'thinking'>('answering')
  const [difficulty, setDifficulty] = useState('medium')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!sessionId) return
    // 启动时后端已生成第一题（由 setup 页跳转带来），此处直接拉取会话初始问题
    // 简单起见：若会话不存在则回到 setup
    setLoading(false)
  }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, phase])

  const push = (role: Msg['role'], content: string) =>
    setMessages((m) => [...m, { id: `${Date.now()}-${Math.random()}`, role, content }])

  const submit = async () => {
    if (!sessionId || !answer.trim() || phase !== 'answering') return
    const text = answer.trim()
    setAnswer('')
    push('user', text)
    setPhase('thinking')
    setError('')
    try {
      const r: InterviewAnswerResp = await interviewApi.answer({ session_id: sessionId, answer: text })
      setDifficulty(r.difficulty)
      setQuestionIndex(r.question_index)
      setTotal(r.total_rounds)
      if (r.interview_finished) {
        push('system', '🎉 面试结束，正在生成评估报告…')
        navigate(`/interview/report/${sessionId}`)
      } else if (r.should_followup) {
        push('interviewer', `🔁 追问：${r.question}`)
        setPhase('answering')
      } else {
        push('interviewer', r.question)
        setPhase('answering')
      }
    } catch (e) {
      setError((e as Error).message)
      setPhase('answering')
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="card p-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-800">模拟面试</h2>
          <p className="text-sm text-gray-500">
            第 {Math.min(questionIndex + 1, total || 1)} / {total || '…'} 题
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-sm text-gray-500">难度</span>
          <span className={`badge-${DIFF_COLOR[difficulty] || 'badge-medium'} px-3 py-1 rounded-full text-xs font-semibold`}>
            {{ easy: '简单', medium: '中等', hard: '困难' }[difficulty] || difficulty}
          </span>
        </div>
      </div>

      <div className="card p-6 min-h-[300px] space-y-4">
        {loading ? (
          <div className="text-center text-gray-500 py-12">加载中…</div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
                  m.role === 'user'
                    ? 'bg-gradient-to-r from-purple-500 to-indigo-600 text-white'
                    : m.role === 'system'
                      ? 'bg-gray-100 text-gray-600'
                      : 'bg-gray-100 text-gray-800'
                }`}
              >
                {m.content}
              </div>
            </div>
          ))
        )}
        {phase === 'thinking' && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl px-4 py-3 text-sm text-gray-500">正在思考…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && <div className="text-sm text-red-500">{error}</div>}

      <div className="card p-4 flex space-x-3">
        <textarea
          className="input-field flex-1 min-h-[60px]"
          placeholder="输入你的回答…"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          disabled={phase !== 'answering'}
        />
        <button className="btn-primary self-end" onClick={submit} disabled={phase !== 'answering'}>
          提交
        </button>
      </div>
    </div>
  )
}
