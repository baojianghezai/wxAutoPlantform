<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Document, ArrowRight, ArrowLeft, Brush, View, Position } from '@element-plus/icons-vue';
import type { Article, CategoryInfo, Template } from '../types';
import { getUnifiedArticles, getTemplates, pushDraft } from '../api';
import StepIndicator from '../components/StepIndicator.vue';
import ArticleCard from '../components/ArticleCard.vue';
import TemplateCard from '../components/TemplateCard.vue';
import PreviewPage from '../components/PreviewPage.vue';

// ---- 状态 ----
const currentStep = ref(1);
const articles = ref<Article[]>([]);
const templates = ref<Template[]>([]);
const categories = ref<CategoryInfo[]>([
  { id: 'recruitment', label: '招聘类' },
  { id: 'agriculture', label: '农业类' },
  { id: 'other', label: '其他' },
]);
const articleTab = ref('recruitment');
const templateTab = ref('recruitment');
const selectedArticleId = ref<string | null>(null);
const selectedTemplateId = ref<string | null>(null);
const loading = ref(false);
const slideDirection = ref<'forward' | 'backward'>('forward');
const navigating = ref(false);

// ---- 派生 ----
const selectedArticle = computed(() =>
  articles.value.find((a) => a.id === selectedArticleId.value) ?? null
);

const selectedTemplate = computed(() =>
  templates.value.find((t) => t.id === selectedTemplateId.value) ?? null
);

const categoryOf = (c?: string) => c || 'other';

const visibleArticles = computed(() =>
  articles.value.filter((a) => categoryOf(a.source_category) === articleTab.value)
);

const visibleTemplates = computed(() =>
  templates.value.filter((t) => categoryOf(t.category) === templateTab.value)
);

const articleCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const a of articles.value) {
    const k = categoryOf(a.source_category);
    counts[k] = (counts[k] || 0) + 1;
  }
  return counts;
});

const templateCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const t of templates.value) {
    const k = categoryOf(t.category);
    counts[k] = (counts[k] || 0) + 1;
  }
  return counts;
});

const canNextStep1 = computed(() => !!selectedArticleId.value);
const canNextStep2 = computed(() => !!selectedArticleId.value && !!selectedTemplateId.value);

// ---- 步骤切换（带滑动动画） ----
function goToStep2() {
  if (!canNextStep1.value || navigating.value) return;
  // 模板 Tab 跟随已选文章的分类
  if (selectedArticle.value) {
    const cat = categoryOf(selectedArticle.value.source_category);
    if (templates.value.some((t) => categoryOf(t.category) === cat)) {
      templateTab.value = cat;
    }
  }
  navigating.value = true;
  slideDirection.value = 'forward';
  currentStep.value = 2;
  setTimeout(() => { navigating.value = false; }, 450);
}

function goBackToStep1() {
  if (navigating.value) return;
  navigating.value = true;
  slideDirection.value = 'backward';
  currentStep.value = 1;
  setTimeout(() => { navigating.value = false; }, 450);
}

function goToStep3() {
  if (!canNextStep2.value || navigating.value) return;
  navigating.value = true;
  slideDirection.value = 'forward';
  currentStep.value = 3;
  setTimeout(() => { navigating.value = false; }, 450);
}

function goBackToStep2() {
  if (navigating.value) return;
  navigating.value = true;
  slideDirection.value = 'backward';
  currentStep.value = 2;
  setTimeout(() => { navigating.value = false; }, 450);
}

// ---- 事件处理 ----
function handleSelectArticle(id: string) {
  selectedArticleId.value = id;
}

function handleSelectTemplate(id: string) {
  selectedTemplateId.value = id;
}

function handleViewUrl(url: string) {
  window.open(url, '_blank');
}

async function handlePush() {
  if (!selectedArticleId.value || !selectedTemplateId.value) return;

  try {
    await ElMessageBox.confirm(
      `确认推送文章「${selectedArticle.value?.title.slice(0, 30)}${(selectedArticle.value?.title.length ?? 0) > 30 ? '...' : ''}」\n使用模板「${selectedTemplate.value?.name}」至公众号草稿箱？`,
      '推送确认',
      {
        confirmButtonText: '确认推送',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false,
      }
    );
  } catch {
    return;
  }

  loading.value = true;
  try {
    const res = await pushDraft({
      articleId: selectedArticleId.value,
      templateId: selectedTemplateId.value,
    });
    console.log('[Push Payload]', {
      articleId: selectedArticleId.value,
      templateId: selectedTemplateId.value,
      response: res,
    });
    ElMessage.success('草稿推送成功！');
  } catch {
    ElMessage.error('推送失败，请重试');
  } finally {
    loading.value = false;
  }
}

// ---- 加载数据 ----
async function loadData() {
  loading.value = true;
  try {
    const [articlesData, templatesData] = await Promise.all([
      getUnifiedArticles(),
      getTemplates(),
    ]);
    articles.value = articlesData.articles;
    templates.value = templatesData.templates;
    if (templatesData.categories.length) {
      categories.value = templatesData.categories;
    }
  } catch {
    ElMessage.error('数据加载失败');
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadData();
});
</script>

<template>
  <div class="dashboard">
    <!-- 顶部栏：步骤指示 + 操作按钮 -->
    <header class="top-bar">
      <div class="bar-left">
        <h1 class="app-title">运营审核发布台</h1>
        <StepIndicator :current-step="currentStep" :total-steps="3" />
      </div>
      <div class="bar-right">
        <!-- 第一步右上角按钮 -->
        <template v-if="currentStep === 1">
          <div class="nav-btn-wrap" @click="goToStep2">
            <el-button type="primary" size="large" :disabled="!canNextStep1">
              下一步：选择模板
              <el-icon class="button-icon"><ArrowRight /></el-icon>
            </el-button>
          </div>
        </template>

        <!-- 第二步右上角按钮 -->
        <template v-if="currentStep === 2">
          <div class="nav-btn-wrap" @click="goBackToStep1">
            <el-button size="large">
              <el-icon class="button-icon"><ArrowLeft /></el-icon>
              返回上一步
            </el-button>
          </div>
          <div class="nav-btn-wrap" @click="goToStep3">
            <el-button type="primary" size="large" :disabled="!canNextStep2">
              下一步：预览确认
              <el-icon class="button-icon"><ArrowRight /></el-icon>
            </el-button>
          </div>
        </template>

        <!-- 第三步右上角按钮 -->
        <template v-if="currentStep === 3">
          <div class="nav-btn-wrap" @click="goBackToStep2">
            <el-button size="large">
              <el-icon class="button-icon"><ArrowLeft /></el-icon>
              返回上一步
            </el-button>
          </div>
          <div class="nav-btn-wrap" @click="handlePush">
            <el-button type="primary" size="large" :loading="loading" :disabled="!canNextStep2">
              <el-icon class="button-icon"><Position /></el-icon>
              推送草稿箱
            </el-button>
          </div>
        </template>
      </div>
    </header>

    <!-- 步骤内容区（滑动动画） -->
    <main class="steps-viewport">
      <div
        class="steps-track"
        :style="{
          transform: `translateX(-${(currentStep - 1) * 33.333}%)`,
          transition: 'transform 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
        }"
      >
        <!-- 第一步：选择文章 -->
        <section class="step-page">
          <div class="page-header">
            <h2 class="page-title">
              <el-icon color="#409eff" :size="20"><Document /></el-icon>
              第一步：选择要发布文章
            </h2>
            <el-text type="info" size="small">共 {{ articles.length }} 篇文章，点击卡片选中</el-text>
          </div>

          <el-tabs v-model="articleTab" class="category-tabs">
            <el-tab-pane
              v-for="cat in categories"
              :key="cat.id"
              :name="cat.id"
            >
              <template #label>
                <span class="tab-label">{{ cat.label }}</span>
                <el-tag size="small" type="info" effect="plain" class="tab-count">
                  {{ articleCounts[cat.id] || 0 }}
                </el-tag>
              </template>
            </el-tab-pane>
          </el-tabs>

          <div class="cards-grid">
            <ArticleCard
              v-for="article in visibleArticles"
              :key="article.id"
              :article="article"
              :selected="article.id === selectedArticleId"
              @select="handleSelectArticle(article.id)"
              @view-url="handleViewUrl"
            />
          </div>
          <el-empty
            v-if="visibleArticles.length === 0 && !loading"
            :description="`暂无${categories.find((c) => c.id === articleTab)?.label || ''}文章`"
          />
        </section>

        <!-- 第二步：选择模板 -->
        <section class="step-page">
          <div class="page-header">
            <h2 class="page-title">
              <el-icon color="#409eff" :size="20"><Brush /></el-icon>
              第二步：选择推送模板
            </h2>
            <el-text type="info" size="small">已选文章：{{ selectedArticle?.title?.slice(0, 30) || '无' }}</el-text>
          </div>

          <el-tabs v-model="templateTab" class="category-tabs">
            <el-tab-pane
              v-for="cat in categories"
              :key="cat.id"
              :name="cat.id"
            >
              <template #label>
                <span class="tab-label">{{ cat.label }}</span>
                <el-tag size="small" type="info" effect="plain" class="tab-count">
                  {{ templateCounts[cat.id] || 0 }}
                </el-tag>
              </template>
            </el-tab-pane>
          </el-tabs>

          <div class="cards-grid template-grid">
            <TemplateCard
              v-for="tpl in visibleTemplates"
              :key="tpl.id"
              :template="tpl"
              :selected="tpl.id === selectedTemplateId"
              @select="handleSelectTemplate(tpl.id)"
            />
          </div>
          <el-empty
            v-if="visibleTemplates.length === 0 && !loading"
            :description="`暂无${categories.find((c) => c.id === templateTab)?.label || ''}模板`"
          />
        </section>

        <!-- 第三步：预览确认 -->
        <section class="step-page">
          <div class="page-header">
            <h2 class="page-title">
              <el-icon color="#409eff" :size="20"><View /></el-icon>
              第三步：预览确认
            </h2>
            <el-text type="info" size="small">确认文章内容与模板样式后推送</el-text>
          </div>
          <PreviewPage
            :article="selectedArticle"
            :template="selectedTemplate"
            :loading="loading"
            @push="handlePush"
            @back="goBackToStep2"
          />
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: #f5f7fa;
}

/* ---- 顶部栏 ---- */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
  padding: 0 20px;
  gap: 20px;
  z-index: 10;
}

.bar-left {
  display: flex;
  align-items: center;
  gap: 24px;
  flex: 1;
  min-width: 0;
}

.app-title {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
  margin: 0;
  white-space: nowrap;
  flex-shrink: 0;
}

.bar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.nav-btn-wrap {
  display: inline-flex;
}

.button-icon {
  margin-right: 2px;
}

/* ---- 步骤视口 ---- */
.steps-viewport {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.steps-track {
  display: flex;
  width: 300%;
  height: 100%;
}

.step-page {
  flex: 0 0 calc(100% / 3);
  height: 100%;
  overflow-y: auto;
  padding: 20px 24px;
  box-sizing: border-box;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ---- 卡片网格 ---- */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}

.template-grid {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

/* ---- 分类 Tab ---- */
.category-tabs {
  margin-bottom: 16px;
}

.tab-label {
  font-weight: 600;
}

.tab-count {
  margin-left: 6px;
  font-weight: 400;
}
</style>
