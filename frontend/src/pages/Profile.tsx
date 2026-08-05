import { useEffect, useState } from 'react'
import { authApi, ProfileData, WrongBookItem } from '../api/auth'
import { getLlmKey, LLM_KEY_STORAGE } from '../api/client'
import { interviewApi } from '../api/interview'
import { practiceApi } from '../api/practice'
import RadarChart from '../components/RadarChart'

interface HistoryItem {
  summary: Record<string, unknown>
}

export default function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [interviews, setInterviews] = useState<HistoryItem[]>([])
  const [practices, setPractices] = useState<HistoryItem[]>([])
  const [wrongs, setWrongs] = useState<WrongBookItem[]>([])
  const [expandedWrong, setExpandedWrong] = useState<number | null>(null)
  // 模型设置（BYOK）
  const [llmKey, setLlmKey] = useState(getLlmKey())
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState('')
  const [hasSavedKey, setHasSavedKey] = useState(Boolean(getLlmKey()))

  useEffect(() => {
    authApi.profile().then(setProfile).catch(() => {})
    interviewApi.history().then((d) => setInterviews(d.items as HistoryItem[])).catch(() => {})
    practiceApi.history().then((d) => setPractices(d.items as HistoryItem[])).catch(() => {})
    // 完整错题本（含答案/参考/笔记）
    authApi.wrongBook().then((d) => setWrongs(d.items)).catch(() => {})
  }, [])

  if (!profile) return <div className="text-center text-gray-500 py-12">加载中…</div>

  const radar = profile.radar_scores || {}

  const saveLlmKey = () => {
    const k = llmKey.trim()
    try {
      if (k) {
        localStorage.setItem(LLM_KEY_STORAGE, k)
        // 写入后回读校验，确保真的保存成功
        if (localStorage.getItem(LLM_KEY_STORAGE) !== k) {
          setHasSavedKey(false)
          setTestResult('⚠️ 保存失败：浏览器拒绝了写入（可能处于无痕/隐私模式或存储被禁用）。Key 不会丢失但本次未保存，请手动记录并稍后重试。')
          return
        }
        setHasSavedKey(true)
        setTestResult('已保存 ✅（仅存于本机浏览器，不会上传服务器）。注意：清除浏览器数据/无痕模式会丢失，建议妥善保管原 Key。')
      } else {
        localStorage.removeItem(LLM_KEY_STORAGE)
        setHasSavedKey(false)
        setTestResult('已清除本机保存的 Key')
      }
    } catch {
      setHasSavedKey(false)
      setTestResult('⚠️ 保存失败：无法写入浏览器存储（无痕模式或存储被禁用）。Key 只在本次页面会话内有效，关闭页面后需重新填写。')
    }
  }

  const testLlm = async () => {
    if (!llmKey.trim()) {
      setTestResult('请先填入 API Key')
      return
    }
    setTesting(true)
    setTestResult('')
    try {
      const r = await authApi.testLlm(llmKey.trim())
      setTestResult(r.ok ? `✅ 连接成功（${r.model}）：${r.response || ''}` : `❌ ${r.error || '连接失败'}`)
    } catch (e) {
      setTestResult(`❌ ${(e as Error).message}`)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 模型设置（BYOK） */}
      <div className="card p-6">
        <h2 className="text-lg font-bold text-gray-800">🔑 模型设置（自带 API Key）</h2>
        <p className="text-sm text-gray-500 mt-1">
          本项目不收取费用、不消耗平台配额。使用 AI 能力需自备 LLM Key（支持 DeepSeek / SiliconFlow 等 OpenAI 兼容服务），
          知识库嵌入已由平台提供免费额度。Key 仅存于你本机浏览器，随请求头发送，服务器不落库。
        </p>
        <div className="mt-3 text-sm">
          {hasSavedKey ? (
            <span className="badge-easy px-3 py-1 rounded-full text-xs font-semibold">已保存 Key（本机）</span>
          ) : (
            <span className="badge-medium px-3 py-1 rounded-full text-xs font-semibold">未配置 Key（AI 功能不可用）</span>
          )}
        </div>
        <div className="flex space-x-3 mt-4">
          <input
            type="password"
            className="input-field flex-1"
            placeholder="粘贴你的 LLM API Key（如 DeepSeek sk-...）"
            value={llmKey}
            onChange={(e) => setLlmKey(e.target.value)}
          />
          <button className="btn-ghost flex-shrink-0" onClick={testLlm} disabled={testing}>
            {testing ? '测试中…' : '测试'}
          </button>
          <button className="btn-primary flex-shrink-0" onClick={saveLlmKey}>保存</button>
        </div>
        {testResult && <div className="text-sm mt-3 text-gray-600">{testResult}</div>}
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
          {wrongs.length === 0 ? (
            <p className="text-sm text-gray-400">{'暂无错题，练习中 < 6 分的题目会自动收录'}</p>
          ) : (
            <div className="space-y-2">
              {wrongs.map((w) => {
                const open = expandedWrong === w.id
                return (
                  <div key={w.id} className="border rounded-xl">
                    <button
                      className="w-full px-4 py-2 flex items-center justify-between text-left hover:bg-gray-50 transition"
                      onClick={() => setExpandedWrong(open ? null : w.id)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-700 truncate">{w.question}</div>
                        <div className="text-xs text-gray-400">{w.topic} · {w.created_at ? new Date(w.created_at).toLocaleDateString() : ''}</div>
                      </div>
                      <span className={`ml-3 text-sm font-semibold ${w.score < 4 ? 'text-red-500' : 'text-yellow-600'}`}>{w.score}/10</span>
                      <span className="ml-2 text-gray-400 text-xs">{open ? '▲' : '▼'}</span>
                    </button>
                    {open && (
                      <div className="px-4 pb-4 space-y-3 text-sm">
                        <div>
                          <div className="font-semibold text-gray-700 mb-1">❓ 题目</div>
                          <div className="text-gray-600">{w.question}</div>
                        </div>
                        <div>
                          <div className="font-semibold text-gray-700 mb-1">✍️ 我的回答</div>
                          <div className="text-gray-600 whitespace-pre-wrap">{w.answer || '（无）'}</div>
                        </div>
                        <div>
                          <div className="font-semibold text-gray-700 mb-1">💯 参考答案</div>
                          <div className="text-gray-600 whitespace-pre-wrap">{w.reference || '（无）'}</div>
                        </div>
                        {w.note && (
                          <div>
                            <div className="font-semibold text-gray-700 mb-1">📝 复习笔记</div>
                            <div className="text-gray-600 whitespace-pre-wrap">{w.note}</div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
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
