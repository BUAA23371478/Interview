import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { interviewApi, InterviewReport as ReportType, StudyPlan } from '../api/interview'
import RadarChart from '../components/RadarChart'

const REC_LABEL: Record<string, string> = {
  strong_hire: '强烈推荐',
  hire: '推荐',
  weak_hire: '勉强',
  no_hire: '不推荐',
}

export default function InterviewReport() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [report, setReport] = useState<ReportType | null>(null)
  const [plan, setPlan] = useState<StudyPlan | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!sessionId) return
    interviewApi.report(sessionId).then((d) => {
      setReport(d.final_report)
      setPlan(d.study_plan ?? null)
    }).catch((e) => setError((e as Error).message))
  }, [sessionId])

  if (error) return <div className="text-red-500">{error}</div>
  if (!report) return <div className="text-center text-gray-500 py-12">报告生成中…</div>

  const dims = report.dimension_scores || {}

  return (
    <div className="space-y-6">
      <div className="card p-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">面试评估报告</h2>
          <p className="text-sm text-gray-500">综合评分 {report.overall_score}/100 · {REC_LABEL[report.recommendation] || report.recommendation}</p>
        </div>
        <div className="w-56 h-56">
          <RadarChart scores={dims} />
        </div>
      </div>

      <div className="card p-6">
        <h3 className="font-bold text-gray-800 mb-3">总体评价</h3>
        <p className="text-sm text-gray-600">{report.summary}</p>
        <p className="mt-3 text-sm text-gray-500">面试官评语：{report.interviewer_comment}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">✅ 优势</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            {report.strengths.map((s, i) => <li key={i}>• {s}</li>)}
          </ul>
          <h3 className="font-bold text-gray-800 mt-4 mb-3">⚠️ 待加强</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            {report.weaknesses.map((s, i) => <li key={i}>• {s}</li>)}
          </ul>
        </div>
        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">📊 维度评分</h3>
          {Object.entries(dims).map(([k, v]) => (
            <div key={k} className="flex items-center space-x-2 mb-2">
              <span className="w-32 text-sm text-gray-600">{k}</span>
              <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-purple-500 to-indigo-600" style={{ width: `${v * 10}%` }} />
              </div>
              <span className="text-sm font-semibold text-purple-600">{v}</span>
            </div>
          ))}
        </div>
      </div>

      {plan && (
        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">📅 4 周复习计划</h3>
          <p className="text-sm text-gray-500 mb-4">{plan.overall_advice}</p>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {plan.weeks.map((w) => (
              <div key={w.week} className="border rounded-xl p-4">
                <div className="text-xs font-bold text-purple-600">第 {w.week} 周</div>
                <div className="font-semibold text-gray-800 mt-1">{w.theme}</div>
                <ul className="text-xs text-gray-500 mt-2 space-y-1">
                  {w.goals.map((g, i) => <li key={i}>• {g}</li>)}
                </ul>
                <div className="text-xs text-gray-400 mt-2">每天 {w.daily_hours}h</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
