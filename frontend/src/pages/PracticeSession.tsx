import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { practiceApi, PracticeAnswerResp, PracticeReport } from '../api/practice'

export default function PracticeSession() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const ragHit = (location.state as { ragHit?: boolean } | null)?.ragHit ?? true
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [phase, setPhase] = useState<'answering' | 'thinking' | 'feedback' | 'done'>('answering')
  const [feedback, setFeedback] = useState<PracticeAnswerResp | null>(null)
  const [report, setReport] = useState<PracticeReport | null>(null)
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
          // 会话已结束，恢复报告
          setReport(r.report ?? null)
          setPhase('done')
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
        // 最后一道题：先展示反馈 + 报告，不直接跳走
        setFeedback(r)
        setReport(r.report ?? null)
        setPhase('done')
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

      {!ragHit && (
        <div className="card p-4 border-l-4 !border-l-yellow-400 bg-yellow-50">
          <p className="text-sm text-yellow-800">
            ⚠️ 知识库暂无该主题的相关资料，AI 将基于通用知识出题。建议先在知识库上传相关文档，出题会更贴合。
          </p>
        </div>
      )}

      <div className="card p-6">
        {phase === 'done' ? (
          <DoneView feedback={feedback} report={report} onBack={() => navigate('/profile')} />
        ) : (
          <>
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
          </>
        )}
      </div>

      {error && <div className="text-sm text-red-500">{error}</div>}

      {phase !== 'feedback' && phase !== 'done' && (
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

function DoneView({
  feedback,
  report,
  onBack,
}: {
  feedback: PracticeAnswerResp | null
  report: PracticeReport | null
  onBack: () => void
}) {
  return (
    <div className="space-y-5">
      <div className="text-center">
        <div className="text-3xl">🎉</div>
        <div className="text-xl font-bold text-gray-800 mt-2">练习完成</div>
        <p className="text-sm text-gray-500 mt-1">
          共 {report?.total_questions ?? 0} 题 · 平均分 {report?.avg_score ?? feedback?.score ?? '-'}/10
        </p>
      </div>

      {feedback && feedback.last_question_score !== undefined && (
        <div className="border rounded-xl p-4 bg-gray-50">
          <div className="font-semibold text-gray-700 mb-2">📝 最后一题反馈</div>
          <div className="flex items-center space-x-2 mb-2">
            <span className="text-2xl font-bold text-purple-600">{feedback.last_question_score}</span>
            <span className="text-gray-500">/ 10 分</span>
            {feedback.last_question_correct ? (
              <span className="badge-easy px-2 py-1 rounded-full text-xs font-semibold">回答正确</span>
            ) : (
              <span className="badge-hard px-2 py-1 rounded-full text-xs font-semibold">需要加强</span>
            )}
          </div>
          {feedback.last_feedback && <div className="text-sm text-gray-600">{feedback.last_feedback}</div>}
          {feedback.last_reference && (
            <div className="text-sm mt-2">
              <div className="font-semibold text-gray-700 mb-1">💯 参考答案</div>
              <div className="text-gray-600 whitespace-pre-wrap">{feedback.last_reference}</div>
            </div>
          )}
        </div>
      )}

      {report && (
        <div className="border rounded-xl p-4">
          <div className="font-semibold text-gray-700 mb-2">📊 练习统计</div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-purple-600">{report.avg_score}</div>
              <div className="text-xs text-gray-500">平均分</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-purple-600">{(report.accuracy * 100).toFixed(0)}%</div>
              <div className="text-xs text-gray-500">正确率</div>
            </div>
          </div>
          {report.topic_performance.length > 0 && (
            <div className="mt-3 text-sm">
              <div className="font-semibold text-gray-600 mb-1">分主题表现</div>
              {report.topic_performance.map((t, i) => (
                <div key={i} className="flex justify-between py-1 border-b border-gray-100 last:border-0">
                  <span className="text-gray-600">{t.topic}</span>
                  <span className={`font-semibold ${t.avg_score >= 6 ? 'text-green-600' : 'text-red-500'}`}>{t.avg_score}/10</span>
                </div>
              ))}
            </div>
          )}
          {report.weaknesses.length > 0 && (
            <div className="mt-3 text-sm text-red-500">⚠️ 待加强：{report.weaknesses.join('、')}</div>
          )}
        </div>
      )}

      <div className="flex justify-center space-x-3">
        <button className="btn-primary" onClick={onBack}>回到个人中心</button>
      </div>
    </div>
  )
}
