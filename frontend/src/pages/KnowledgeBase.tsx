import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  FileText,
  Search,
  Trash2,
  Upload,
  Loader2,
  RefreshCw,
  X,
} from 'lucide-react';
import { knowledgeApi } from '@/api/knowledge';
import type { KnowledgeDoc } from '@/api/knowledge';

const CATEGORY_OPTIONS = [
  '未分类',
  '编程语言',
  '框架与工具',
  '计算机基础',
  '系统设计',
  'AI/ML',
  '行业面经',
];

const KnowledgeBase: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 文档列表状态
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filterCategory, setFilterCategory] = useState<string | undefined>();

  // 上传状态
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [uploadOk, setUploadOk] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('未分类');
  const [customCategory, setCustomCategory] = useState('');
  const [docTitle, setDocTitle] = useState('');

  // 搜索状态
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<{ content: string; metadata: Record<string, unknown>; score: number }[]>([]);

  // 删除中
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // 分类列表
  const [categories, setCategories] = useState<string[]>([]);

  // 加载文档列表
  const loadDocs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await knowledgeApi.list(1, 100, filterCategory);
      setDocs(data.items);
      setTotal(data.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filterCategory]);

  // 加载分类
  const loadCategories = useCallback(async () => {
    try {
      const data = await knowledgeApi.categories();
      setCategories(data.categories);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadDocs();
    loadCategories();
  }, [loadDocs, loadCategories]);

  // 上传文件
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 校验类型
    const allowed = ['.pdf', '.md', '.markdown', '.txt'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      setUploadMsg(`不支持的文件类型: ${ext}，支持 PDF/MD/TXT`);
      setUploadOk(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    // 校验大小 (50MB)
    if (file.size > 50 * 1024 * 1024) {
      setUploadMsg('文件过大，限制 50MB');
      setUploadOk(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setUploading(true);
    setUploadMsg('');
    const category = customCategory || selectedCategory;

    try {
      const result = await knowledgeApi.upload(file, category, docTitle || undefined);
      if (result.ok) {
        setUploadMsg(`✅ ${result.filename} 上传成功，已索引 ${result.chunkCount} 个片段`);
        setUploadOk(true);
        setDocTitle('');
        loadDocs();
        loadCategories();
      } else {
        setUploadMsg(`❌ ${result.error || '上传失败'}`);
        setUploadOk(false);
      }
    } catch (err: unknown) {
      setUploadMsg(`❌ ${(err as { message?: string }).message || '上传失败'}`);
      setUploadOk(false);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // 删除文档
  const handleDelete = async (doc: KnowledgeDoc) => {
    if (!window.confirm(`确定删除「${doc.filename}」？将同时清除其向量索引。`)) return;
    setDeletingId(doc.id);
    try {
      await knowledgeApi.remove(doc.id);
      loadDocs();
      loadCategories();
    } catch {
      // ignore
    } finally {
      setDeletingId(null);
    }
  };

  // 重建索引
  const handleReindex = async (doc: KnowledgeDoc) => {
    setDeletingId(doc.id);
    try {
      const result = await knowledgeApi.reindex(doc.id);
      if (result.ok) {
        setUploadMsg(`✅ ${doc.filename} 索引重建完成（${result.chunkCount} 片段）`);
        setUploadOk(true);
        loadDocs();
      }
    } catch {
      // ignore
    } finally {
      setDeletingId(null);
    }
  };

  // 搜索
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const data = await knowledgeApi.search(searchQuery.trim(), 5, filterCategory);
      setSearchResults(data.items);
    } catch {
      // ignore
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* 返回 */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> 返回首页
      </button>

      {/* 标题 */}
      <div className="text-center mb-8">
        <div className="inline-flex p-3 rounded-xl bg-amber-100 mb-4">
          <BookOpen className="w-7 h-7 text-amber-600" />
        </div>
        <h1 className="text-2xl font-bold text-slate-800 mb-2">知识库管理</h1>
        <p className="text-slate-500 text-sm">
          上传技术文档构建知识库，RAG 检索增强刷题与面试出题质量
        </p>
      </div>

      {/* ---- 上传区域 ---- */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
        <h2 className="text-base font-semibold text-slate-700 mb-4 flex items-center gap-2">
          <Upload className="w-4 h-4" /> 上传文档
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          {/* 分类 */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">分类</label>
            <div className="flex gap-2">
              <select
                value={customCategory ? '__custom__' : selectedCategory}
                onChange={(e) => {
                  if (e.target.value === '__custom__') return;
                  setSelectedCategory(e.target.value);
                  setCustomCategory('');
                }}
                className="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                {CATEGORY_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
                <option value="__custom__">自定义...</option>
              </select>
            </div>
            {customCategory !== '' || (!CATEGORY_OPTIONS.includes(selectedCategory) && selectedCategory !== '') ? (
              <input
                type="text"
                value={customCategory || selectedCategory}
                onChange={(e) => { setCustomCategory(e.target.value); setSelectedCategory(''); }}
                placeholder="输入自定义分类"
                className="mt-1 w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            ) : null}
          </div>

          {/* 标题 */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">标题（可选，默认用文件名）</label>
            <input
              type="text"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              placeholder="文档标题"
              className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
        </div>

        {/* 文件上传按钮 */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleUpload}
          accept=".pdf,.md,.markdown,.txt"
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="w-full py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all duration-200 flex items-center justify-center gap-2"
        >
          {uploading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" /> 解析索引中...
            </>
          ) : (
            <>
              <FileText className="w-4 h-4" /> 选择文件上传（PDF / MD / TXT）
            </>
          )}
        </button>
        <p className="text-xs text-slate-400 mt-2 text-center">
          支持 PDF、Markdown、纯文本，最大 50MB。上传后自动分块、向量化、存入知识库。
        </p>
        {uploadMsg && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${
            uploadOk ? 'bg-green-50 border border-green-200 text-green-700' : 'bg-red-50 border border-red-200 text-red-600'
          }`}>
            {uploadMsg}
          </div>
        )}
      </div>

      {/* ---- 搜索区域 ---- */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
        <h2 className="text-base font-semibold text-slate-700 mb-4 flex items-center gap-2">
          <Search className="w-4 h-4" /> 知识库检索
        </h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="输入关键词搜索知识库..."
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-500 transition-all"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="px-5 py-2.5 bg-slate-700 hover:bg-slate-800 disabled:bg-slate-300 text-white text-sm font-medium rounded-xl transition-colors flex items-center gap-1.5"
          >
            {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            搜索
          </button>
        </div>

        {/* 搜索结果 */}
        {searchResults.length > 0 && (
          <div className="mt-4 space-y-3">
            {searchResults.map((item, i) => (
              <div key={i} className="p-3 rounded-xl bg-amber-50 border border-amber-100">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-amber-700 bg-amber-200 px-2 py-0.5 rounded-full">
                    相关度 {(item.score * 100).toFixed(0)}%
                  </span>
                  <span className="text-xs text-slate-400">
                    {String(item.metadata?.filename || '未知来源')}
                  </span>
                </div>
                <p className="text-sm text-slate-700 leading-relaxed line-clamp-4">{item.content}</p>
              </div>
            ))}
          </div>
        )}
        {searchResults.length === 0 && searchQuery && !searching && (
          <p className="text-sm text-slate-400 mt-3 text-center">未找到相关结果</p>
        )}
      </div>

      {/* ---- 文档列表 ---- */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-slate-700 flex items-center gap-2">
            <FileText className="w-4 h-4" /> 已上传文档
            {total > 0 && (
              <span className="text-xs font-normal text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
                {total} 个
              </span>
            )}
          </h2>
          <select
            value={filterCategory || ''}
            onChange={(e) => setFilterCategory(e.target.value || undefined)}
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-600"
          >
            <option value="">全部分类</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <div className="text-center py-8 text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
            加载中...
          </div>
        ) : docs.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">知识库为空</p>
            <p className="text-xs mt-1">上传技术文档后，RAG 检索将自动增强出题和评估质量</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between p-3 rounded-xl hover:bg-slate-50 transition-colors border border-slate-100"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-700 truncate">
                      {doc.title || doc.filename}
                    </span>
                    <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full shrink-0">
                      {doc.category}
                    </span>
                    <span className="text-xs text-slate-300 uppercase shrink-0">{doc.fileType}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                    <span>{doc.chunkCount} 个索引片段</span>
                    <span>{(doc.charCount / 1000).toFixed(1)}k 字符</span>
                    {doc.fileSizeMb > 0 && <span>{doc.fileSizeMb.toFixed(1)} MB</span>}
                    {doc.createdAt && (
                      <span>{new Date(doc.createdAt).toLocaleDateString('zh-CN')}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 ml-3 shrink-0">
                  <button
                    onClick={() => handleReindex(doc)}
                    disabled={deletingId === doc.id}
                    className="p-2 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors disabled:opacity-50"
                    title="重建索引"
                  >
                    <RefreshCw className={`w-4 h-4 ${deletingId === doc.id ? 'animate-spin' : ''}`} />
                  </button>
                  <button
                    onClick={() => handleDelete(doc)}
                    disabled={deletingId === doc.id}
                    className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                    title="删除"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default KnowledgeBase;
