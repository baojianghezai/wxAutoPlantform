<script setup lang="ts">
defineProps<{
  currentStep: number;
  totalSteps: number;
}>();
</script>

<template>
  <div class="step-indicator">
    <div
      v-for="step in totalSteps"
      :key="step"
      class="step-item"
      :class="{ active: step === currentStep, done: step < currentStep }"
    >
      <div class="step-circle">
        <el-icon v-if="step < currentStep" class="step-check"><Check /></el-icon>
        <span v-else class="step-num">{{ step }}</span>
      </div>
      <div class="step-label">
        {{ step === 1 ? '选择文章' : step === 2 ? '选择模板' : '预览确认' }}
      </div>
      <div
        v-if="step < totalSteps"
        class="step-line"
        :class="{ done: step < currentStep }"
      />
    </div>
  </div>
</template>

<style scoped>
.step-indicator {
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  gap: 0;
}

.step-item {
  display: flex;
  align-items: center;
  position: relative;
  flex: 1;
}

.step-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e0e0e0;
  color: #999;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  transition: all 0.3s;
}

.step-item.active .step-circle {
  background: #409eff;
  color: #fff;
}

.step-item.done .step-circle {
  background: #67c23a;
  color: #fff;
}

.step-check {
  font-size: 14px;
}

.step-num {
  font-size: 13px;
}

.step-label {
  font-size: 13px;
  color: #999;
  margin-left: 8px;
  white-space: nowrap;
  transition: color 0.3s;
}

.step-item.active .step-label {
  color: #409eff;
  font-weight: 500;
}

.step-item.done .step-label {
  color: #67c23a;
}

.step-line {
  flex: 1;
  height: 2px;
  background: #e0e0e0;
  margin: 0 12px;
  transition: background 0.3s;
}

.step-line.done {
  background: #67c23a;
}
</style>
