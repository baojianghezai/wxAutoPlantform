<script setup lang="ts">
import type { Template } from '../types';

defineProps<{
  template: Template;
  selected: boolean;
}>();

const emit = defineEmits<{
  (e: 'select'): void;
}>();

function handleClick() {
  emit('select');
}
</script>

<template>
  <div
    class="template-card"
    :class="{ 'is-selected': selected }"
    @click="handleClick"
  >
    <!-- 模板本地预览图 -->
    <div class="phone-thumb-wrapper">
      <img
        v-if="template.previewImage"
        :src="template.previewImage"
        alt=""
        class="preview-img"
      />
      <div v-else class="thumb-placeholder">
        <el-icon :size="24" color="#c0c4cc"><Picture /></el-icon>
      </div>
    </div>

    <!-- 底部信息 -->
    <div class="card-footer">
      <span class="template-name">{{ template.name }}</span>
      <el-tag
        v-if="selected"
        size="small"
        type="primary"
        effect="dark"
        class="selected-tag"
      >
        <el-icon><Check /></el-icon> 已选
      </el-tag>
    </div>

    <!-- 选中角标 -->
    <div v-if="selected" class="selected-badge">
      <el-icon color="#fff" :size="14"><Check /></el-icon>
    </div>
  </div>
</template>

<style scoped>
.template-card {
  position: relative;
  background: #fff;
  border: 2px solid #e0e0e0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s ease;
  overflow: hidden;
}

.template-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.template-card.is-selected {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.15);
  background: #fafcff;
}

.phone-thumb-wrapper {
  width: 100%;
  height: 200px;
  overflow: hidden;
  background: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 本地预览图：等比缩放铺满，避免撑破卡片 */
.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ebeef5;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-top: 1px solid #f0f0f0;
}

.template-name {
  font-size: 13px;
  font-weight: 600;
}

.selected-tag {
  border: none;
  font-size: 10px;
}

.selected-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  background: #409eff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
}
</style>
