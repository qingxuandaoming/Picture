import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import pinia from './stores'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import './styles/main.css'

const app = createApp(App)

// 注册所有Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(router)
app.use(pinia)
app.mount('#app')

