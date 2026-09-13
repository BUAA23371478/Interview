import { useEffect, useState } from 'react'
import { authApi, ProfileData, WrongBookItem } from '../api/auth'
import { interviewApi } from '../api/interview'
import { practiceApi } from '../api/practice'
import RadarChart from '../components/RadarChart'

interface HistoryItem {
  summary: Record<string, unknown>
}

interface CreditsInfo {
  maoo_user_id: number
  balance: number
  yuan: number
  total_consumed: number
  total_granted: number
  total_recharged: number
  frozen: number
}

export default function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [interviews, setInterviews] = useState<HistoryItem[]>([])
  const [practices, setPractices] = useState<HistoryItem[]>([])
  const [wrongs, setWrongs] = useState<WrongBookItem[]>([])
  const [expandedWrong, setExpandedWrong] = useState<number | null>(null)
  const [credits, setCredits] = useState<CreditsInfo | null>(null)
  const [topUpCredits, setTopUpCredits] = useState(10_000)   // 默认充 10 元 = 10000 积分
  const [topUpMsg, setTopUpMsg] = useState('')
  const [topUpBusy, setTopUpBusy] = useState(false)

  useEffect(() => {
    authApi.profile().then(setProfile).catch(() => {})
    interviewApi.history().then((d) => setInterviews(d.items as HistoryItem[])).catch(() => {})
    practiceApi.history().then((d) => setPractices(d.items as HistoryItem[])).catch(() => {})
    // 完整错题本（含答案/参考/笔记）
    authApi.wrongBook().then((d) => setWrongs(d.items)).catch(() => {})
    authApi.credits().then(setCredits).catch(() => {})
  }, [])

  if (!profile) return <div className="text-center text-gray-500 py-12">加载中…</div>

  const radar = profile.radar_scores || {}

  const topUp = async () => {
    if (topUpCredits <= 0) {
      setTopUpMsg('积分必须为正整数')
      return
    }
    setTopUpBusy(true)
    setTopUpMsg('')
    try {
      const r = await authApi.recharge({ credits: topUpCredits })
      if (r.ok && r.balance != null) {
        setTopUpMsg(`✅ 充值成功：+${r.credits} 积分（≈ ¥${r.yuan}），余额 ${r.balance}`)
        setCredits({
          maoo_user_id: credits?.maoo_user_id ?? 0,
          balance: r.balance,
          yuan: r.yuan ?? 0,
          total_consumed: credits?.total_consumed ?? 0,
          total_granted: credits?.total_granted ?? 0,
          total_recharged: (credits?.total_recharged ?? 0) + (r.credits ?? 0),
          frozen: credits?.frozen ?? 0,
        })
      } else {
        setTopUpMsg(`❌ ${r.message ?? '充值失败'}`)
      }
    } catch (e) {
      setTopUpMsg(`❌ ${(e as Error).message}`)
    } finally {
      setTopUpBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 积分账户 */}
      <div className="card p-6">
        <h2 className="text-lg font-bold text-gray-800">💰 积分账户</h2>
        <p className="text-sm text-gray-500 mt-1">
          平台托管 LLM Key，你只需购买积分即可使用 AI 能力（1 元 = 1000 积分，按 token 计费）。
        </p>
        <div className="grid grid-cols-3 gap-4 mt-4">
          <Stat label="当前余额（积分）" value={credits?.balance ?? '-'} />
          <Stat label="累计消耗（积分）" value={credits?.total_consumed ?? '-'} />
          <Stat label="累计充值（积分）" value={credits?.total_recharged ?? '-'} />
        </div>
        <div className="flex space-x-3 mt-4 items-end">
          <div className="flex-1">
            <label className="text-xs text-gray-500">充值积分（1 元 = 1000）</label>
            <input
              type="number"
              className="input-field w-full mt-1"
              min={1}
              step={1000}
              value={topUpCredits}
              onChange={(e) => setTopUpCredits(parseInt(e.target.value || '0', 10))}
            />
          </div>
          <button className="btn-primary flex-shrink-0" onClick={topUp} disabled={topUpBusy}>
            {topUpBusy ? '处理中…' : '充值（mock）'}
          </button>
        </div>
        {topUpMsg && <div className="text-sm mt-3 text-gray-600">{topUpMsg}</div>}
        <p className="text-xs text-gray-400 mt-2">
          当前为占位实现，不会接入真实支付。生产环境接支付后此处会显示真实收银台。
        </p>
      </div>
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
            <Stat label="累计刷题" value={profile.total_practices} />
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
          {wrongs.map((w) => (
            <div key={w.id} className="border rounded-xl p-3 text-sm">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="font-medium text-gray-700">{w.topic}</div>
                  <div className="text-xs text-gray-500 mt-1">{w.question}</div>
                </div>
                <span className="text-purple-600 font-semibold ml-2">{w.score}</span>
              </div>
              {expandedWrong === w.id && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  <div className="text-xs text-gray-500">你的答案</div>
                  <div className="text-sm text-gray-700 mt-1 whitespace-pre-wrap">{w.answer || '（未作答）'}</div>
                  <div className="text-xs text-gray-500 mt-2">参考答案</div>
                  <div className="text-sm text-gray-700 mt-1 whitespace-pre-wrap">{w.reference || '（暂无）'}</div>
                </div>
              )}
              <button
                onClick={() => setExpandedWrong(expandedWrong === w.id ? null : w.id)}
                className="text-xs text-purple-600 mt-2"
              >
                {expandedWrong === w.id ? '收起' : '查看详情'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-xl font-bold text-gray-800 mt-1">{value}</div>
    </div>
  )
}