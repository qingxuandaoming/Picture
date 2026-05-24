<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import request from '../utils/request'
import { ElMessage } from 'element-plus'

const tasks = ref([])
const pollingTimer = ref(null)
const currentTaskId = ref(null)

const getTasks = async () => {
  try {
    const data = await request.get('/batch/tasks')
    if (data && data.length > 0) {
      // 倒序排列，最新的任务放在最上方
      data.sort((a, b) => {
        const timeA = a.create_time || ''
        const timeB = b.create_time || ''
        return timeB.localeCompare(timeA)
      })
      tasks.value = data
    } else {
      // 如果没有任务，显示示例任务
      tasks.value = [
        {
          id: 'sample1',
          name: '规则分类任务 - 500张',
          status: 'completed',
          progress: 100,
          create_time: new Date().toLocaleString(),
          total: 500,
          processed: 500,
          renamed: 0,
          reclassified: 320,
          errors: 0,
          skipped: 0
        }
      ]
    }
  } catch (error) {
    console.error('获取任务列表失败')
    // 显示示例任务
    tasks.value = [
      {
        id: 'sample1',
        name: '规则分类任务 - 500张',
        status: 'completed',
        progress: 100,
        create_time: new Date().toLocaleString(),
        total: 500,
        processed: 500,
        renamed: 0,
        reclassified: 320,
        errors: 0,
        skipped: 0
      }
    ]
  }
}

const checkTaskProgress = async () => {
  if (!currentTaskId.value) return

  try {
    const data = await request.get(`/batch/progress/${currentTaskId.value}`)
    // 更新任务列表中的对应任务
    const taskIndex = tasks.value.findIndex(t => t.id === currentTaskId.value)
    if (taskIndex !== -1) {
      tasks.value[taskIndex] = { ...tasks.value[taskIndex], ...data }

      // 如果任务完成或被取消，停止轮询
      if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
        stopPolling()
        if (data.status === 'completed') ElMessage.success('任务完成！')
        else if (data.status === 'failed') ElMessage.error('任务失败')
        else ElMessage.info('任务已取消')
      }
    } else {
      // 如果是新任务，添加到列表
      tasks.value.unshift(data)
    }
  } catch (error) {
    console.error('获取任务进度失败')
  }
}

const startPolling = (taskId) => {
  currentTaskId.value = taskId
  stopPolling()
  checkTaskProgress() // 立即检查一次
  pollingTimer.value = setInterval(checkTaskProgress, 2000)
}

const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

const cancelTask = async (taskId) => {
  try {
    await request.post(`/batch/cancel/${taskId}`)
    ElMessage.success('已发出取消指令')
    if (currentTaskId.value === taskId) {
      checkTaskProgress()
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '取消失败')
  }
}

const getStatusType = (status) => {
  switch (status) {
    case 'completed': return 'success'
    case 'processing': return 'primary'
    case 'failed': return 'danger'
    case 'cancelled': return 'info'
    default: return 'info'
  }
}

const getStatusText = (status) => {
  switch (status) {
    case 'completed': return '已完成'
    case 'processing': return '处理中'
    case 'failed': return '失败'
    case 'cancelled': return '已取消'
    default: return '等待中'
  }
}

const getResultClass = (res) => {
  if (res.success) {
    if (res.reclassified) return 'text-yellow-400'
    return 'text-green-400'
  }
  if (res.skipped) return 'text-gray-400'
  return 'text-red-400'
}

const getResultStatus = (res) => {
  if (res.success) return '成功'
  if (res.skipped) return '跳过'
  return '失败'
}

const getResultMessage = (res) => {
  const parts = [`文件: ${res.original_path.split(/[\\/]/).pop()}`]
  if (res.error) parts.push(`错误: ${res.error}`)
  else if (res.skipped) parts.push(`原因: 已处理过`)
  else {
    if (res.new_name) parts.push(`=> ${res.new_name}`)
    if (res.category && res.category !== res.original_category) parts.push(`[分类: ${res.original_category} -> ${res.category}]`)
    else if (res.category) parts.push(`[分类: ${res.category}]`)
    if (res.description) parts.push(`[描述: ${res.description}]`)
  }
  return parts.join(' ')
}

onMounted(() => {
  getTasks().then(() => {
    // 检查是否有刚创建的任务
    const recentTaskId = localStorage.getItem('currentTaskId')
    if (recentTaskId) {
      localStorage.removeItem('currentTaskId')
      startPolling(recentTaskId)
    } else {
      // 自动查找是否有正在处理的任务，并自动开始轮询
      const processingTask = tasks.value.find(t => t.status === 'processing')
      if (processingTask && !pollingTimer.value) {
        startPolling(processingTask.id)
      }
    }
  })
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>任务中心</h1>
      <p>查看和管理批量处理任务，实时追踪进度</p>
    </div>

    <!-- 任务列表卡片 -->
    <div class="space-y-6">
      <div v-for="task in tasks" :key="task.id" class="card">
        <div class="flex justify-between items-start mb-6">
          <div>
            <h3 class="text-xl font-bold">{{ task.name }}</h3>
            <p class="text-sm opacity-70 mt-1">{{ task.create_time }}</p>
          </div>
          <el-tag :type="getStatusType(task.status)" size="large">
            {{ getStatusText(task.status) }}
          </el-tag>
        </div>

        <!-- 进度条 -->
        <div class="mb-6">
          <div class="flex justify-between items-center mb-3">
            <span class="font-medium">处理进度</span>
            <span class="font-bold text-lg">{{ task.progress }}%</span>
          </div>
          <el-progress :percentage="task.progress" :stroke-width="12" :show-text="false" />
        </div>

        <!-- 统计数据 -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div class="p-4 rounded-xl" style="background: rgba(199, 177, 152, 0.1)">
            <p class="text-2xl font-bold">
              <span v-if="task.status === 'processing' && task.total === 0" class="text-base animate-pulse">正在扫描图片...</span>
              <span v-else>{{ task.total }}</span>
            </p>
            <p class="text-sm opacity-70">总数量</p>
          </div>
          <div class="p-4 rounded-xl" style="background: rgba(154, 171, 185, 0.1)">
            <p class="text-2xl font-bold">{{ task.processed }}</p>
            <p class="text-sm opacity-70">已处理</p>
          </div>
          <div class="p-4 rounded-xl" style="background: rgba(165, 196, 165, 0.1)">
            <p class="text-2xl font-bold">{{ task.renamed || 0 }}</p>
            <p class="text-sm opacity-70">已重命名</p>
          </div>
          <div class="p-4 rounded-xl" style="background: rgba(196, 165, 196, 0.1)">
            <p class="text-2xl font-bold">{{ task.reclassified || 0 }}</p>
            <p class="text-sm opacity-70">已重分类</p>
          </div>
          <div class="p-4 rounded-xl" style="background: rgba(212, 165, 165, 0.1)">
            <p class="text-2xl font-bold">{{ task.errors || 0 }}</p>
            <p class="text-sm opacity-70">失败</p>
          </div>
        </div>

        <!-- 处理日志终端窗口 -->
        <div v-if="task.status === 'processing' || (task.results && task.results.length > 0)" class="mt-6 bg-[#1e1e1e] rounded-xl p-4 flex flex-col h-64 border border-gray-800">
          <div class="flex items-center text-xs text-gray-500 mb-3 pb-2 border-b border-gray-800">
            <span class="w-2 h-2 rounded-full bg-red-500 mr-2"></span>
            <span class="w-2 h-2 rounded-full bg-yellow-500 mr-2"></span>
            <span class="w-2 h-2 rounded-full bg-green-500 mr-3"></span>
            处理日志终端 (Terminal)
          </div>
          <div class="flex-1 overflow-y-auto font-mono text-[13px] space-y-1.5 scrollbar-thin scrollbar-thumb-gray-700 leading-relaxed pr-2 flex flex-col-reverse">
            <div>
              <div v-for="(res, index) in task.results" :key="index" :class="getResultClass(res)">
                [{{ getResultStatus(res) }}] {{ getResultMessage(res) }}
              </div>
              <div v-for="file in task.processing_files" :key="'proc_' + file" class="text-blue-400 animate-pulse">
                [处理中] 正在分析: {{ file }} ...
              </div>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="mt-6 flex gap-3">
          <el-button 
            type="primary" 
            :disabled="task.status === 'processing' && currentTaskId === task.id" 
            @click="startPolling(task.id)"
          >
            {{ task.status === 'processing' && currentTaskId === task.id ? '实时刷新中...' : '刷新进度' }}
          </el-button>
          
          <el-popconfirm
            v-if="task.status === 'processing'"
            title="确定要取消此任务吗？已处理的图片进度会保留。"
            confirm-button-text="确定取消"
            cancel-button-text="放弃"
            confirm-button-type="danger"
            @confirm="cancelTask(task.id)"
          >
            <template #reference>
              <el-button type="danger" plain>
                取消任务
              </el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
}
.grid-cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.md\:grid-cols-5 {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}
.gap-4 {
  gap: 16px;
}
.space-y-6 > * + * {
  margin-top: 24px;
}
.p-4 {
  padding: 16px;
}
.rounded-xl {
  border-radius: 12px;
}
.flex {
  display: flex;
}
.gap-3 {
  gap: 12px;
}
.justify-between {
  justify-content: space-between;
}
.items-start {
  align-items: flex-start;
}
.items-center {
  align-items: center;
}
.text-xl {
  font-size: 20px;
}
.text-lg {
  font-size: 18px;
}
.text-2xl {
  font-size: 28px;
}
.text-sm {
  font-size: 14px;
}
.font-bold {
  font-weight: bold;
}
.font-medium {
  font-weight: 500;
}
.opacity-70 {
  opacity: 0.7;
}
.mt-1 {
  margin-top: 4px;
}
.mb-6 {
  margin-bottom: 24px;
}
.mt-6 {
  margin-top: 24px;
}
</style>
