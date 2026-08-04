import { useEffect, useState } from 'react'
import { authApi, ProfileData } from '../api/auth'
import { interviewApi } from '../api/interview'
import { practiceApi } from '../api/practice'
import RadarChart from '../components/RadarChart'

interface HistoryItem {
  summary: Record<string, unknown>
}

interface WrongItem {
  id: number
  topic: string
  question: string
  score: number
  reviewed: number
  note: string
  created_at: string | null
}

export default function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [interviews, setInterviews] = useState<HistoryItem[]>([])
  const [practices, setPractices] = useState<HistoryItem[]>([])
  const [wrongs, setWrongs] = useState<WrongItem[]>([])

  useEffect(() => {
    authApi.profile().then(setProfile).catch(() => {})
    interviewApi.history().then((d) => setInterviews(d.items as HistoryItem[])).catch(() => {})
    practiceApi.history().then((d) => setPractices(d.items as HistoryItem[])).catch(() => {})
    // 从画像取错题本（简化为展示画像中的 wrong_book）
    authApi.profile().then((p) => setWrongs(p.wrong_book.map((w, i) => ({
      id: i,
      topic: String((w as { topic?: unknown }).topic ?? ''),
      question: String((w as { question?: unknown }).question ?? ''),
      score: Number((w as { score?: unknown }).score ?? 0),
      reviewed: 0,
      note: '',
      created_at: null,
    }))))
  }, [])

  if (!profile) return <div className="text-center text-gray-500 py-12">加载中…</div>

  const radar = profile.radar_scores || {}

  return (
    <div className="space-y-6">
      <div className="card p-6 flex items-center space-x-8">
        <div className="w-52 h-52 flex-shrink-0">
          {Object.keys(radar).length > 0 ? (
            <RadarChart scores={radar} />
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400 text-sm">完成一次面试后生成雷达图</div>
          )}
        </div>
        <div className="flex-1">
          <h2 className="text-2xl font-bold text-gray-800">个人画像</h2>
          <div className="grid grid-cols-3 gap-4 mt-4">
            <Stat label="模拟面试" value={profile.total_interviews} />
            <Stat label="专项练习" value={profile.total_practices} />
            <Stat label="平均分" value={profile.avg_score.toFixed(1)} />
          </div>
          <div className="mt-4">
            <div className="text-sm font-semibold text-gray-700 mb-2">技术优势</div>
            <div className="flex flex-wrap gap-2">
              {profile.tech_strengths.length > 0 ? (
                profile.tech_strengths.map((s, i) => <span key={i} className="skill-tag">{s}</span>)
              ) : (
                <span className="text-xs text-gray-400">暂无标注</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">⚠️ 薄弱点（跨会话记忆）</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            {profile.persistent_weaknesses.length > 0 ? (
              profile.persistent_weaknesses.map((w, i) => <li key={i}>• {w}</li>)
            ) : (
              <li className="text-gray-400">暂无，完成面试后自动沉淀</li>
            )}
          </ul>
        </div>
        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">📖 面试记录（{interviews.length}）</h3>
          <div className="space-y-2 max-h-[220px] overflow-y-auto">
            {interviews.map((it, i: number) => (
              <div key={i} className="border rounded-xl px-3 py-2 text-sm">
                <div className="flex justify-between">
                  <span className="font-medium text-gray-700">面试 #{i + 1}</span>
                  <span className="text-purple-600 font-semibold">{String((it.summary as { overall_score?: unknown })?.overall_score ?? '-')}</span>
                </div>
                <div className="text-xs text-gray-400">推荐：{String((it.summary as { recommendation?: unknown })?.recommendation ?? '-')}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">🏷️ 练习记录（{practices.length}）</h3>
          <div className="space-y-2 max-h-[220px] overflow-y-auto">
            {practices.map((it, i: number) => (
              <div key={i} className="border rounded-xl px-3 py-2 text-sm">
                <div className="flex justify-between">
                  <span className="font-medium text-gray-700">{String((it.summary as { topic?: unknown })?.topic ?? `练习 #${i + 1}`)}</span>
                  <span className="text-purple-600 font-semibold">{String((it.summary as { avg_score?: unknown })?.avg_score ?? '-')}</span>
                </div>
                <div className="text-xs text-gray-400">{String((it.summary as { total_questions?: unknown })?.total_questions ?? '-')} 题</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="font-bold text-gray-800 mb-3">📕 错题本（{wrongs.length}）</h3>
        <div className="space-y-2 max-h-[260px] overflow-y-auto">
          {wrongs.length === 0 ? (
            <p className="text-sm text-gray-400">{'暂无错题，练习中 < 6 分的题目会自动收录'}</p>
          ) : (
            wrongs.map((w, i) => (
              <div key={i} className="border rounded-xl px-4 py-2 flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-700 truncate">{w.question}</div>
                  <div className="text-xs text-gray-400">{w.topic}</div>
                </div>
                <span className={`ml-3 text-sm font-semibold ${w.score < 4 ? 'text-red-500' : 'text-yellow-600'}`}>{w.score}/10</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="text-center border rounded-xl py-3">
      <div className="text-2xl font-bold text-purple-600">{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  )
}
