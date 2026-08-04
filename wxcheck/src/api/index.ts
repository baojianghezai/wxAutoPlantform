import type { PushPayload, Template, UnifiedResponse } from '../types';

/**
 * 后端接口说明（本地 Flask 服务，默认 http://localhost:5001，5000 被 Docker RSS 占用）：
 * - GET  /api/articles  → 统一契约 JSON（schema_version 1.0）：
 *   { schema_version, source_system, scope, generated_at, stats, articles }
 * - GET  /api/templates → { code: 0, templates: Template[] }
 * - POST /api/submit    → body JSON { article_id, template_id }，
 *   响应 { code: 0, msg } 成功 / { code: 1, msg } 失败
 *
 * 开发环境下 vite dev server 已将 /api 代理到 Flask（见 vite.config.ts），
 * 因此 BASE_URL 默认为空字符串（相对路径）；可通过环境变量 VITE_API_BASE 覆盖。
 */
const BASE_URL = import.meta.env.VITE_API_BASE ?? '';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${url}`, init);
  if (!res.ok) {
    throw new Error(`请求失败：HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getUnifiedArticles(): Promise<UnifiedResponse> {
  return request<UnifiedResponse>('/api/articles');
}

interface TemplatesResponse {
  code: number;
  templates: Template[];
}

export async function getTemplates(): Promise<Template[]> {
  const data = await request<TemplatesResponse>('/api/templates');
  return data.templates;
}

export async function pushDraft(payload: PushPayload): Promise<{ code: number; msg: string }> {
  const data = await request<{ code: number; msg: string }>('/api/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      article_id: payload.articleId,
      template_id: payload.templateId,
    }),
  });
  if (data.code !== 0) {
    throw new Error(data.msg || '推送失败');
  }
  return data;
}
