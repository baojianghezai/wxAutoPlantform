<script setup lang="ts">
import { computed } from 'vue';
import type { Article } from '../types';

const props = defineProps<{
  article: Article;
  selected: boolean;
}>();

const emit = defineEmits<{
  (e: 'select'): void;
  (e: 'view-url', url: string): void;
}>();

const sourceTypeLabel = computed(() =>
  props.article.source_type === 'wechat' ? '公众号' : '网页'
);

const sourceTypeColor = computed(() =>
  props.article.source_type === 'wechat' ? 'warning' : 'info'
);

function handleCardClick() {
  emit('select');
}

function handleViewUrl(e: Event) {
  e.stopPropagation();
  emit('view-url', props.article.url);
}
</script>

<template>
  <div
    class="article-card"
    :class="{ 'is-selected': selected }"
    @click="handleCardClick"
  >
    <!-- 内容 -->
    <div class="card-body">
      <div class="card-title">{{ article.title }}</div>

      <div class="card-tags">
        <el-tag type="info" size="small" effect="plain">{{ article.category }}</el-tag>
        <el-tag v-if="article.direction" size="small" effect="plain" type="success">
          {{ article.direction }}
        </el-tag>
        <el-tag :type="sourceTypeColor" size="small" effect="plain">{{ sourceTypeLabel }}</el-tag>
      </div>

      <div class="card-meta">
        <span class="meta-source">{{ article.source }}</span>
        <span class="meta-sep">|</span>
        <span class="meta-date">{{ article.published_at || '未知日期' }}</span>
      </div>

      <el-button
        size="small"
        text
        type="primary"
        @click="handleViewUrl"
      >
        <el-icon class="button-icon"><Link /></el-icon>
        查看原文
      </el-button>
    </div>

    <!-- 选中标记 -->
    <div v-if="selected" class="selected-badge">
      <el-icon color="#409eff" :size="18"><Check /></el-icon>
    </div>
  </div>
</template>

<style scoped>
.article-card {
  position: relative;
  display: flex;
  background: #fff;
  border: 2px solid #e0e0e0;
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.25s ease;
}

.article-card:hover {
  border-color: #c0c4cc;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}

.article-card.is-selected {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.12);
  background: #f0f7ff;
}

.card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
}

.meta-sep {
  color: #e0e0e0;
}

.button-icon {
  margin-right: 2px;
}

.selected-badge {
  position: absolute;
  top: -1px;
  right: -1px;
  width: 24px;
  height: 24px;
  background: #409eff;
  border-radius: 0 8px 0 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
