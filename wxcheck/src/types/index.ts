export interface Article {
  id: string;
  title: string;
  source: string;
  source_type: 'web' | 'wechat';
  direction: string;
  category: string;
  source_category?: string;
  published_at: string;
  url: string;
  summary: string;
  thumbnail: string;
  extra?: Record<string, unknown>;
}

export interface Template {
  id: string;
  name: string;
  content_type: string;
  content_type_label: string;
  category?: string;
  category_label?: string;
  style: string;
  description: string;
  previewHtml: string;
  previewImage: string;
}

export interface CategoryInfo {
  id: string;
  label: string;
}

export interface UnifiedResponse {
  schema_version: string;
  source_system: string;
  scope: string;
  generated_at: string;
  stats: { web_total: number; wechat_total: number; total: number };
  categories?: CategoryInfo[];
  articles: Article[];
}

export interface PushPayload {
  articleId: string;
  templateId: string;
}
