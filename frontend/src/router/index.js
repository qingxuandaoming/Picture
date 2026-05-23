import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/dashboard'
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { title: '仪表盘', icon: 'Odometer' }
  },
  {
    path: '/image',
    name: 'ImageProcess',
    component: () => import('../views/ImageProcess.vue'),
    meta: { title: '图片处理', icon: 'Picture' }
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('../views/Tasks.vue'),
    meta: { title: '任务中心', icon: 'List' }
  },
  {
    path: '/categories',
    name: 'Categories',
    component: () => import('../views/Categories.vue'),
    meta: { title: '分类管理', icon: 'FolderOpened' }
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('../views/Config.vue'),
    meta: { title: '配置中心', icon: 'Setting' }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
