# 运营审核发布台 - Claude Code 执行框架（基于真实爬虫接口）

> **技术栈**：Vue 3 (Composition API + `<script setup>`) + TypeScript + Vite + Element Plus
> **目标**：基于 `爬虫接口文档.md` 中的 `unified_articles.json` 数据结构，构建三栏审核发布页面。

---

## 一、数据对接说明（请仔细阅读）

接口文档中的核心数据结构如下（已简化）：

```typescript
interface UnifiedResponse {
  schema_version: string;
  source_system: string;
  scope: string;
  generated_at: string;
  stats: { web_total: number; wechat_total: number; total: number };
  articles: Article[];
}

interface Article {
  id: string;          // 唯一标识，回传后端用
  title: string;
  source: string;      // 信源名称
  source_type: 'web' | 'wechat';
  direction: string;   // 内容方向（如“劳动法规解读”）
  category: string;    // 板块（如“政策法规” / “公众号招聘”）
  published_at: string; // YYYY-MM-DD
  url: string;         // 原文链接
  summary: string;     // 摘要（可能为空）
  thumbnail: string;   // 缩略图（可能为空）
  extra?: object;      // 仅 wechat 有，暂不处理
}
```