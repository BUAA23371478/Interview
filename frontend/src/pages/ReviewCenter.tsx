import { useEffect, useState } from 'react'
import { kbApi, ReviewItem } from '../api/kb'

export default function ReviewCenter() {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [note, setNote] = useState<Record<number, string>>({})
  const [msg, setMsg] = useState('')

  const load = async () => {
    try {
      const d = await kbApi.pending(1, 50)
      setItems(d.items)
    } catch (e) {
      setMsg(`❌ ${(e as Error).message}`)
    }
  }

  useEffect(() => { load() }, [])

  const review = async (id: number, action: 'approve' | 'reject') => {
    try {
      const r = await kbApi.review(id, action, note[id] || '')
      setMsg(`✅ ${r.message}`)
      load()
    } catch (e) {
      setMsg(`❌ ${(e as Error).message}`)
    }
  }

  if (items.length === 0) {
    return (
      <div className="max-w-3xl mx-auto card p-8 text-center">
        <h2 className="text-xl font-bold text-gray-800 mb-2">审核中心</h2>
        <p className="text-gray-500">没有待审核的文档</p>
        {msg && <p className="text-sm mt-2 text-gray-600">{msg}</p>}
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">审核中心</h2>
        <p className="text-sm text-gray-500">待审核文档（{items.length}）· 已通过 AI 预审，需人工复核</p>
      </div>
      {msg && <div className="text-sm text-gray-600">{msg}</div>}
      {items.map((d) => {
        const pre = (d.ai_precheck as { is_tech_related?: boolean; has_harmful_content?: boolean; approve_score?: number; reason?: string; recommended_category?: string }) || {}
        return (
          <div key={d.id} className="card p-6">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-bold text-gray-800">{d.title}</h3>
                <p className="text-xs text-gray-500">上传者 #{d.maoo_user_id} · {d.filename} · {d.char_count} 字</p>
              </div>
              <span className="badge-medium px-2 py-0.5 rounded-full text-xs">待审核</span>
            </div>

            <div className="mt-4 bg-purple-50 rounded-xl p-4 text-sm">
              <div className="font-semibold text-purple-700 mb-1">🤖 AI 预审结果</div>
              <div className="flex flex-wrap gap-3 text-gray-700">
                <span>技术相关：{pre.is_tech_related ? '✅' : '❌'}</span>
                <span>有害内容：{pre.has_harmful_content ? '⚠️ 有' : '无'}</span>
                <span>预审分：<b>{pre.approve_score ?? '-'}</b></span>
                <span>推荐分类：{pre.recommended_category || '-'}</span>
              </div>
              {pre.reason && <div className="text-gray-500 mt-1">{pre.reason}</div>}
            </div>

            <div className="mt-3 border rounded-xl p-3 bg-gray-50 max-h-[160px] overflow-y-auto text-xs text-gray-500">
              {d.review_logs.map((lg, i) => (
                <div key={i} className="mb-1">
                  <span className="font-semibold">{lg.action}</span> by {lg.reviewer_role} — {lg.note}
                </div>
              ))}
            </div>

            <div className="mt-4 flex space-x-3">
              <input
                className="input-field flex-1 text-sm"
                placeholder="审核备注（可选）"
                value={note[d.id] || ''}
                onChange={(e) => setNote({ ...note, [d.id]: e.target.value })}
              />
              <button className="btn-ghost !text-red-500" onClick={() => review(d.id, 'reject')}>拒绝</button>
              <button className="btn-primary" onClick={() => review(d.id, 'approve')}>通过并入库</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
