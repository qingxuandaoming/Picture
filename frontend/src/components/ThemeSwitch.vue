<script setup>
import { ref } from 'vue'

const currentTheme = ref('morandi')

const themes = [
  { id: 'morandi', name: '莫兰迪浅色', icon: 'Sunny' },
  { id: 'deepdark', name: '深邃黑色', icon: 'Moon' }
]

const changeTheme = (themeId) => {
  currentTheme.value = themeId
  document.body.className = `theme-${themeId}`
  localStorage.setItem('preferred-theme', themeId)
}

const initTheme = () => {
  const saved = localStorage.getItem('preferred-theme')
  if (saved && ['morandi', 'deepdark'].includes(saved)) {
    changeTheme(saved)
  } else {
    changeTheme('morandi')
  }
}

initTheme()
</script>

<template>
  <div class="theme-switch-inline" @click="changeTheme(currentTheme === 'morandi' ? 'deepdark' : 'morandi')" :title="currentTheme === 'morandi' ? '切换深色模式' : '切换浅色模式'">
    <el-icon :size="20">
      <component :is="themes.find(t => t.id === currentTheme)?.icon || 'Sunny'" />
    </el-icon>
  </div>
</template>

<style scoped>
.theme-switch-inline {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.25s ease;
  color: var(--text-secondary);
  margin: 0 auto;
}

.theme-switch-inline:hover {
  background: var(--progress-bg);
  color: var(--text-primary);
  transform: scale(1.05);
}
</style>
