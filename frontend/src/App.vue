<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import request from './utils/request'
import { ElMessage } from 'element-plus'
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

// 初始化引导逻辑
const initDialogVisible = ref(false)
const initLoading = ref(false)
const initForm = ref({
  api_key: '',
  base_dir: 'e:\\Picture',
  default_model: 'doubao-seed-2-0-lite-260428',
  api_endpoint: 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
})

const checkInit = async () => {
  try {
    const res = await request.get('/system/check_init')
    if (res && !res.initialized) {
      initDialogVisible.value = true
    }
  } catch (err) {
    console.error('检查初始化状态失败', err)
  }
}

const submitInit = async () => {
  if (!initForm.value.api_key) {
    ElMessage.warning('API 密钥不能为空')
    return
  }
  if (!initForm.value.base_dir) {
    ElMessage.warning('照片目录不能为空')
    return
  }
  
  initLoading.value = true
  try {
    const defaultCfg = {
      accounts: [
        { name: "默认账号", keys: [initForm.value.api_key] }
      ],
      api_endpoint: initForm.value.api_endpoint,
      default_model: initForm.value.default_model,
      base_dir: initForm.value.base_dir,
      batch_size: 500,
      max_retries: 3
    }
    
    await request.post('/config', defaultCfg)
    ElMessage.success('初始化成功！')
    initDialogVisible.value = false
    
    setTimeout(() => {
      window.location.reload()
    }, 500)
  } catch (err) {
    ElMessage.error('初始化失败，请重试')
  } finally {
    initLoading.value = false
  }
}

onMounted(() => {
  initTheme()
  checkInit()
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

    <!-- 全局初始化引导弹窗 -->
    <el-dialog
      v-model="initDialogVisible"
      title="🚀 欢迎使用 AI图片智能重命名与分类系统"
      width="500px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <div style="margin-bottom: 20px;">
        <p>系统检测到尚未完成基础配置，请跟随引导完成初始设置：</p>
      </div>
      
      <el-form :model="initForm" label-position="top">
        <el-form-item label="1. 火山引擎 API Key (必需)">
          <el-input v-model="initForm.api_key" placeholder="请输入您的 API 密钥..." type="password" show-password />
        </el-form-item>
        
        <el-form-item label="2. 照片根目录 (需处理图片所在文件夹)">
          <el-input v-model="initForm.base_dir" placeholder="例如：e:\Picture" />
        </el-form-item>
        
        <el-collapse accordion style="margin-top: 15px;">
          <el-collapse-item title="高级设置 (可选)" name="1">
            <el-form-item label="默认模型名">
              <el-input v-model="initForm.default_model" />
            </el-form-item>
            <el-form-item label="API 访问端点">
              <el-input v-model="initForm.api_endpoint" />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button type="primary" :loading="initLoading" @click="submitInit" style="width: 100%; height: 40px; font-size: 16px;">
            保存并开启探索
          </el-button>
        </span>
      </template>
    </el-dialog>
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
