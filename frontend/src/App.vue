<script setup>
import { useRouter, useRoute } from 'vue-router'
import { ref, onMounted } from 'vue'
import ThemeSwitch from './components/ThemeSwitch.vue'

const router = useRouter()
const route = useRoute()

const menuItems = ref([
  { path: '/dashboard', title: '仪表盘', icon: 'Odometer' },
  { path: '/image', title: '图片处理', icon: 'Picture' },
  { path: '/tasks', title: '任务中心', icon: 'List' },
  { path: '/categories', title: '分类管理', icon: 'FolderOpened' },
  { path: '/config', title: '配置中心', icon: 'Setting' }
])

const isActive = (path) => {
  return route.path === path
}

const initTheme = () => {
  const saved = localStorage.getItem('preferred-theme')
  if (saved && ['morandi', 'deepdark'].includes(saved)) {
    document.body.className = `theme-${saved}`
  } else {
    document.body.className = 'theme-morandi'
  }
}

onMounted(() => {
  initTheme()
})
</script>

<template>
  <div class="app-container">
    <!-- 侧边栏 - 图标导航栏 -->
    <div class="sidebar">
      <div class="sidebar-logo">
        <div class="logo-icon">AI</div>
      </div>

      <nav class="sidebar-nav">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ 'nav-item-active': isActive(item.path) }"
          :title="item.title"
        >
          <el-icon :size="22"><component :is="item.icon" /></el-icon>
          <span class="nav-tooltip">{{ item.title }}</span>
        </router-link>
      </nav>

      <div class="sidebar-bottom">
        <ThemeSwitch />
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="main-content">
      <router-view />
      
      <footer class="app-footer">
        <p>程序开发者：陈冠衡 | 年份：2026</p>
        <p>
          <a href="https://github.com/qingxuandaoming" target="_blank">GitHub 主页</a> | 
          QQ 邮箱：<a href="mailto:925342921@qq.com">925342921@qq.com</a>
        </p>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.app-footer {
  text-align: center;
  padding: 20px;
  color: var(--text);
  font-size: 14px;
  border-top: 1px solid var(--border);
  margin-top: 20px;
}
.app-footer a {
  color: var(--accent);
  text-decoration: none;
}
.app-footer a:hover {
  text-decoration: underline;
}
</style>
