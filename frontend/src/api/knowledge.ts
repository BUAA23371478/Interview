import api from './client';

export interface KnowledgeDoc {
  id: number;
  filename: string;
  title: string;
  category: string;
  fileType: string;
  chunkCount: number;
  charCount: number;
  fileSizeMb: number;
  createdAt: string | null;
}

export interface KnowledgeListResponse {
  ok: boolean;
  total: number;
  page: number;
  limit: number;
  items: KnowledgeDoc[];
}

export interface KnowledgeSearchItem {
  content: string;
  metadata: Record<string, unknown>;
  score: number;
}

export interface KnowledgeSearchResponse {
  ok: boolean;
  query: string;
  total: number;
  items: KnowledgeSearchItem[];
}

export interface KnowledgeCategoriesResponse {
  ok: boolean;
  categories: string[];
}

export const knowledgeApi = {
  /** 上传文档 */
  upload: (
    file: File,
    category: string = '未分类',
    title?: string,
  ): Promise<{ ok: boolean; docId?: number; filename?: string; chunkCount?: number; charCount?: number; error?: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    if (title) formData.append('title', title);
    return api.upload('/knowledge/upload', formData);
  },

  /** 文档列表 */
  list: (page: number = 1, limit: number = 50, category?: string): Promise<KnowledgeListResponse> => {
    let endpoint = `/knowledge/list?page=${page}&limit=${limit}`;
    if (category) endpoint += `&category=${encodeURIComponent(category)}`;
    return api.get(endpoint);
  },

  /** 删除文档 */
  remove: (docId: number): Promise<{ ok: boolean; error?: string }> => {
    return api.delete(`/knowledge/${docId}`);
  },

  /** 重建索引 */
  reindex: (docId: number): Promise<{ ok: boolean; chunkCount?: number; error?: string }> => {
    return api.post(`/knowledge/${docId}/reindex`);
  },

  /** 搜索知识库 */
  search: (q: string, topK: number = 5, category?: string): Promise<KnowledgeSearchResponse> => {
    let endpoint = `/knowledge/search?q=${encodeURIComponent(q)}&top_k=${topK}`;
    if (category) endpoint += `&category=${encodeURIComponent(category)}`;
    return api.get(endpoint);
  },

  /** 获取分类列表 */
  categories: (): Promise<KnowledgeCategoriesResponse> => {
    return api.get('/knowledge/categories');
  },
};
