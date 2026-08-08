<script setup lang="ts">
import { computed, watch } from 'vue';
import type { Article, Template, WechatAccount } from '../types';

const props = defineProps<{
  article: Article | null;
  template: Template | null;
  accounts: WechatAccount[];
  accountId: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'push'): void;
  (e: 'back'): void;
  (e: 'update:accountId', id: string): void;
}>();

// 模板 style 为后端返回的风格标签（字符串），预览统一使用默认配色
const displayStyle = {
  backgroundColor: '#ffffff',
  color: '#333333',
  borderColor: '#e0e0e0',
  borderRadius: '16px',
} as const;

const hasArticle = computed(() => !!props.article);
const articleTitle = computed(() => {
  if (!props.article) return '';
  const t = props.article.title;
  return t.length > 20 ? t.slice(0, 20) + '...' : t;
});

// 目标公众号展示：默认取第一个已配置账号
const availableAccounts = computed(() =>
  props.accounts.length ? props.accounts : []
);

const selectedAccount = computed(() =>
  availableAccounts.value.find((a) => a.id === props.accountId) ?? null
);

watch(
  () => props.accounts,
  (list) => {
    if (!props.accountId && list.length) {
      const first = list.find((a) => a.configured) ?? list[0];
      if (first) emit('update:accountId', first.id);
    }
  },
  { immediate: true }
);

function handleAccountChange(id: string) {
  emit('update:accountId', id);
}

// 外链缩略图走后端代理，避免 mmbiz 防盗链加载失败
const thumbUrl = computed(() => {
  if (!props.article?.thumbnail) return '';
  return `/api/img?url=${encodeURIComponent(props.article.thumbnail)}`;
});

function handlePush() {
  emit('push');
}

function handleBack() {
  emit('back');
}
</script>

<template>
  <div class="preview-page">
    <!-- 顶部提示 -->
    <div class="preview-hint" v-if="hasArticle">
      已选择 <el-text type="primary" tag="strong">{{ articleTitle }}</el-text>
      &nbsp;·&nbsp;模板：<el-text type="primary" tag="strong">{{ template?.name }}</el-text>
    </div>

    <!-- 目标公众号选择 -->
    <div class="account-row" v-if="hasArticle">
      <el-text size="small" class="account-label">推送至公众号：</el-text>
      <el-select
        :model-value="accountId"
        placeholder="选择目标公众号"
        size="default"
        class="account-select"
        @update:model-value="handleAccountChange"
      >
        <el-option
          v-for="acc in availableAccounts"
          :key="acc.id"
          :label="acc.name + (acc.appid_masked ? `（${acc.appid_masked}）` : '')"
          :value="acc.id"
          :disabled="!acc.configured"
        />
      </el-select>
    </div>

    <!-- 手机模型 -->
    <div class="phone-stage">
      <div class="phone-frame">
        <!-- 手机顶部状态栏 -->
        <div class="phone-status-bar">
          <span>12:30</span>
          <div class="status-icons">
            <el-icon :size="12"><Signal /></el-icon>
            <el-icon :size="12"><Wifi /></el-icon>
            <el-icon :size="12"><BatteryFull /></el-icon>
          </div>
        </div>

        <!-- 手机内容区 -->
        <div class="phone-content-wrapper">
          <div v-if="hasArticle" class="phone-content" :style="displayStyle">
            <!-- 缩略图 -->
            <div class="preview-thumb">
              <img v-if="thumbUrl" :src="thumbUrl" alt="" />
              <div v-else class="thumb-ph">
                <el-icon :size="28" color="#c0c4cc"><Picture /></el-icon>
              </div>
            </div>

            <!-- 标题 -->
            <div class="preview-title">{{ article!.title }}</div>

            <!-- 摘要 -->
            <div class="preview-summary">
              {{ article!.summary || '（该文章无摘要，请点击查看原文）' }}
            </div>

            <!-- 来源信息 -->
            <div class="preview-meta">
              <span>{{ article!.source }}</span>
              <span class="dot">·</span>
              <span>{{ article!.published_at || '未知' }}</span>
            </div>

            <!-- 模板标签 -->
            <div class="preview-tpl-tag">
              <el-tag
                size="small"
                :color="displayStyle.borderColor"
                :text-color="displayStyle.color"
                effect="dark"
              >
                {{ template?.name }}
              </el-tag>
            </div>
          </div>

          <!-- 空态 -->
          <div v-else class="preview-empty">
            <el-icon :size="40" color="#ddd"><Document /></el-icon>
            <p>请选择文章和模板</p>
          </div>
        </div>

        <!-- 手机底部导航条 -->
        <div class="phone-home-bar" />
      </div>
    </div>

    <!-- 底部操作按钮 -->
    <div class="preview-actions" v-if="hasArticle">
      <el-button size="large" :disabled="loading" @click="handleBack">
        <el-icon class="btn-icon"><ArrowLeft /></el-icon>
        上一步
      </el-button>
      <el-button type="primary" size="large" :loading="loading" :disabled="!selectedAccount" @click="handlePush">
        <el-icon class="btn-icon"><Position /></el-icon>
        {{ selectedAccount ? `确认推送至${selectedAccount.name}` : '请选择目标公众号' }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.preview-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
}

.preview-hint {
  flex-shrink: 0;
  font-size: 13px;
  color: #606266;
  margin-bottom: 10px;
  padding: 8px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.account-row {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  width: 100%;
  max-width: 420px;
}

.account-label {
  white-space: nowrap;
  color: #606266;
}

.account-select {
  flex: 1;
}

.phone-stage {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  overflow: auto;
}

.phone-frame {
  width: 360px;
  flex-shrink: 0;
  background: #1a1a1a;
  border-radius: 36px;
  padding: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
}

.phone-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 20px 4px;
  color: #fff;
  font-size: 12px;
  font-weight: 500;
}

.status-icons {
  display: flex;
  gap: 6px;
  align-items: center;
}

.phone-content-wrapper {
  background: #f0f0f0;
  border-radius: 24px;
  overflow-y: auto;
  max-height: 500px;
  min-height: 400px;
}

.phone-content {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.4s ease;
}

.preview-thumb {
  width: 100%;
  height: 160px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  background: #f5f5f5;
}

.preview-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-ph {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ebeef5;
}

.preview-title {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.preview-summary {
  font-size: 12.5px;
  line-height: 1.8;
  flex: 1;
  word-break: break-all;
  opacity: 0.75;
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  opacity: 0.6;
  padding-top: 6px;
  border-top: 1px solid rgba(128, 128, 128, 0.15);
}

.dot {
  font-size: 16px;
  line-height: 1;
}

.preview-tpl-tag {
  align-self: flex-start;
}

.phone-home-bar {
  height: 24px;
  margin: 8px 40px 4px;
  background: #333;
  border-radius: 12px;
}

.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
  color: #c0c4cc;
  font-size: 13px;
  gap: 8px;
}

.preview-actions {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}

.btn-icon {
  margin-right: 2px;
}
</style>
