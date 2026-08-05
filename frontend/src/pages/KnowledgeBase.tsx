import { useCallback, useEffect, useState } from 'react'
import { kbApi, KnowledgeDoc, SearchHit } from '../api/kb'

export default function KnowledgeBase() {
  const [categories, setCategories] = useState<string[]>([])
  const [category, setCategory] = useState('')
  const [docs, setDocs] = useState<KnowledgeDoc[]>([])
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [searching, setSearching] = useState(false)
  // 上传
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')
  const [myDocs, setMyDocs] = useState<KnowledgeDoc[]>([])

  const loadDocs = useCallback(async () => {
    const d = await kbApi.docs(1, 50, undefined, category || undefined)
    setDocs(d.items)
  }, [category])

  useEffect(() => {
    kbApi.categories().then((d) => setCategories(d.categories)).catch(() => {})
    loadDocs()
    // 我的上传：只看当前用户自己上传的（不含内置 seed）
    kbApi.docs(1, 100, undefined, undefined, true).then((d) => setMyDocs(d.items)).catch(() => {})
  }, [loadDocs])

  const doSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await kbApi.search(query.trim(), 10, category || undefined)
      setHits(r.items)
    } finally {
      setSearching(false)
    }
  }

  const onUpload = async (file: File, title: string, cat: string) => {
    setUploading(true)
    setUploadMsg('')
    try {
      const r = await kbApi.upload(file, cat, title)
      setUploadMsg(r.ok ? `✅ ${r.message}（AI 预审分 ${(r.ai_precheck as { approve_score?: number })?.approve_score ?? '-'}）` : `❌ ${r.message}`)
      loadDocs()
      kbApi.docs(1, 100, undefined, undefined, true).then((d) => setMyDocs(d.items)).catch(() => {})
    } catch (e) {
      setUploadMsg(`❌ ${(e as Error).message}`)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">知识库</h2>
          <p className="text-sm text-gray-500">300+ 面试题 · 14 家公司面经 · 支持上传技术文档</p>
        </div>
      </div>

      <div className="card p-6">
        <div className="flex space-x-3">
          <input
            className="input-field flex-1"
            placeholder="搜索知识库，例如：Transformer 自注意力 / Redis 分布式锁…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doSearch()}
          />
          <button className="btn-primary" onClick={doSearch} disabled={searching}>{searching ? '搜索中…' : '搜索'}</button>
        </div>
        <div className="flex flex-wrap gap-2 mt-3">
          <button
            className={`px-3 py-1 rounded-full text-xs border ${!category ? 'bg-purple-100 border-purple-400 text-purple-700' : 'border-gray-200 text-gray-600'}`}
            onClick={() => setCategory('')}
          >
            全部
          </button>
          {categories.map((c) => (
            <button
              key={c}
              className={`px-3 py-1 rounded-full text-xs border ${category === c ? 'bg-purple-100 border-purple-400 text-purple-700' : 'border-gray-200 text-gray-600'}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {hits.length > 0 && (
        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">🔍 搜索结果（{hits.length}）</h3>
          <div className="space-y-3">
            {hits.map((h) => (
              <div key={h.id} className="border rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-purple-700 text-sm">{h.doc_title || '未命名'}</span>
                  <span className="text-xs text-gray-400">{h.category}</span>
                </div>
                <p className="text-sm text-gray-600 mt-2 whitespace-pre-wrap">{h.content.slice(0, 300)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 card p-6">
          <h3 className="font-bold text-gray-800 mb-3">📚 已上架文档（{docs.length}）</h3>
          <div className="space-y-2 max-h-[400px] overflow-y-auto">
            {docs.map((d) => (
              <div key={d.id} className="flex items-center justify-between border rounded-xl px-4 py-2">
                <div>
                  <div className="font-medium text-sm text-gray-800">{d.title}</div>
                  <div className="text-xs text-gray-400">{d.category} · {d.chunk_count} 分块</div>
                </div>
                <span className="badge-easy px-2 py-0.5 rounded-full text-xs">已上架</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h3 className="font-bold text-gray-800 mb-3">📤 上传文档</h3>
          <UploadForm onUpload={onUpload} uploading={uploading} categories={categories} />
          {uploadMsg && <div className="text-xs mt-3 text-gray-600">{uploadMsg}</div>}
          <div className="mt-4 border-t pt-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">我的上传（{myDocs.length}）</h4>
            <div className="space-y-1 max-h-[200px] overflow-y-auto">
              {myDocs.map((d) => (
                <div key={d.id} className="flex items-center justify-between text-xs">
                  <span className="text-gray-600 truncate">{d.title}</span>
                  <StatusBadge status={d.status} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function UploadForm({
  onUpload,
  uploading,
  categories,
}: {
  onUpload: (file: File, title: string, cat: string) => void
  uploading: boolean
  categories: string[]
}) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [cat, setCat] = useState('')
  return (
    <div className="space-y-3">
      <input type="file" accept=".md,.markdown,.txt,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs" />
      <input className="input-field text-sm" placeholder="标题（可选）" value={title} onChange={(e) => setTitle(e.target.value)} />
      <input className="input-field text-sm" placeholder="分类（可选，如 Agent / RAG）" value={cat} onChange={(e) => setCat(e.target.value)} list="kb-cats" />
      <datalist id="kb-cats">
        {categories.map((c) => <option key={c} value={c} />)}
      </datalist>
      <button
        className="btn-primary w-full text-sm"
        disabled={!file || uploading}
        onClick={() => file && onUpload(file, title, cat)}
      >
        {uploading ? '上传中…' : '提交审核'}
      </button>
      <p className="text-[11px] text-gray-400">支持 md/txt/pdf，≤50MB。上传后经 AI 预审与管理员复核，通过后入库。</p>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { cls: string; label: string }> = {
    pending: { cls: 'bg-yellow-100 text-yellow-700', label: '审核中' },
    approved: { cls: 'bg-green-100 text-green-600', label: '已上架' },
    rejected: { cls: 'bg-red-100 text-red-600', label: '已拒绝' },
    removed: { cls: 'bg-gray-100 text-gray-500', label: '已下架' },
  }
  const s = map[status] || map.pending
  return <span className={`${s.cls} px-2 py-0.5 rounded-full`}>{s.label}</span>
}
