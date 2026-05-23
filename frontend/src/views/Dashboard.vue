<script setup>
import { ref, onMounted, computed } from 'vue'
import request from '../utils/request'
import { useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent
} from 'echarts/components'

use([
  CanvasRenderer,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent
])

const router = useRouter()
const stats = ref({
  total_files: 0,
  total_processed: 0,
  category_stats: {}
})

// 检测当前主题
const isDarkMode = computed(() => document.body.classList.contains('theme-deepdark'))

// 浅色/深色模式下的颜色
const lightColors = {
  tooltipBg: 'rgba(255, 255, 255, 0.95)',
  tooltipBorder: 'rgba(0, 0, 0, 0.1)',
  tooltipText: '#333',
  legendText: '#666',
  itemBorder: '#fff',
  labelText: '#333'
}

const darkColors = {
  tooltipBg: 'rgba(22, 28, 45, 0.95)',
  tooltipBorder: 'rgba(148, 163, 184, 0.2)',
  tooltipText: '#f0f4f8',
  legendText: '#8b9bb4',
  itemBorder: '#1e293b',
  labelText: '#f0f4f8'
}

const getColors = () => isDarkMode.value ? darkColors : lightColors

const chartOption = ref({
  tooltip: {
    trigger: 'item',
    formatter: '{a} <br/>{b}: {c} ({d}%)',
    backgroundColor: lightColors.tooltipBg,
    borderColor: lightColors.tooltipBorder,
    textStyle: {
      color: lightColors.tooltipText
    }
  },
  legend: {
    orient: 'vertical',
    left: 'left',
    textStyle: {
      color: lightColors.legendText
    }
  },
  series: [
    {
      name: '图片数量',
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 12,
        borderColor: lightColors.itemBorder,
        borderWidth: 3
      },
      label: {
        show: false,
        position: 'center'
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 16,
          fontWeight: 'bold',
          color: lightColors.labelText
        }
      },
      labelLine: {
        show: false
      },
      data: []
    }
  ]
})

// 更新图表颜色
const updateChartColors = () => {
  const colors = getColors()
  chartOption.value.tooltip.backgroundColor = colors.tooltipBg
  chartOption.value.tooltip.borderColor = colors.tooltipBorder
  chartOption.value.tooltip.textStyle.color = colors.tooltipText
  chartOption.value.legend.textStyle.color = colors.legendText
  chartOption.value.series[0].itemStyle.borderColor = colors.itemBorder
  chartOption.value.series[0].emphasis.label.color = colors.labelText
}

// 深色模式下使用蓝色系
const getStatCardColors = (isDark) => {
  if (isDark) {
    return [
      { startColor: '#3b82f6', endColor: '#2563eb', rgb: '59, 130, 246' },    // 蓝色
      { startColor: '#0ea5e9', endColor: '#0284c7', rgb: '14, 165, 233' },    // 天蓝
      { startColor: '#10b981', endColor: '#059669', rgb: '16, 185, 129' },    // 绿色
      { startColor: '#f59e0b', endColor: '#d97706', rgb: '245, 158, 11' }     // 琥珀
    ]
  }
  return [
    { startColor: '#c7b198', endColor: '#a8907c', rgb: '199, 177, 152' },
    { startColor: '#9aabb9', endColor: '#7a8a99', rgb: '154, 171, 185' },
    { startColor: '#a5c4a5', endColor: '#85a485', rgb: '165, 196, 165' },
    { startColor: '#d4a5a5', endColor: '#b98c8c', rgb: '212, 165, 165' }
  ]
}

const statCards = ref([
  {
    title: '总图片数',
    value: 0,
    icon: 'Picture',
    startColor: '#c7b198',
    endColor: '#a8907c',
    rgb: '199, 177, 152'
  },
  {
    title: '已处理数',
    value: 0,
    icon: 'Check',
    startColor: '#9aabb9',
    endColor: '#7a8a99',
    rgb: '154, 171, 185'
  },
  {
    title: '分类数量',
    value: 18,
    icon: 'FolderOpened',
    startColor: '#a5c4a5',
    endColor: '#85a485',
    rgb: '165, 196, 165'
  },
  {
    title: '处理成功率',
    value: '0%',
    icon: 'SuccessFilled',
    startColor: '#d4a5a5',
    endColor: '#b98c8c',
    rgb: '212, 165, 165'
  }
])

// 更新统计卡片颜色
const updateStatCardColors = () => {
  const colors = getStatCardColors(isDarkMode.value)
  statCards.value.forEach((card, index) => {
    card.startColor = colors[index].startColor
    card.endColor = colors[index].endColor
    card.rgb = colors[index].rgb
  })
}

const getStats = async () => {
  try {
    const data = await request.get('/stats')
    stats.value = data

    statCards.value[0].value = data.total_files
    // 确保已处理数量不会超过总数量（去重处理）
    const processedCount = Math.min(data.total_processed, data.total_files)
    statCards.value[1].value = processedCount
    // 使用后端计算的任务成功率
    const successRate = data.success_rate || 0
    statCards.value[3].value = `${successRate}%`

    // 更新图表数据
    const chartData = []
    for (const [cat, count] of Object.entries(data.category_stats)) {
      if (count > 0) {
        chartData.push({ name: cat, value: count })
      }
    }
    chartOption.value.series[0].data = chartData
  } catch (error) {
    console.error('获取统计数据失败:', error)
  }
}

const goToProcess = () => {
  router.push('/image')
}

onMounted(() => {
  updateStatCardColors()
  updateChartColors()
  getStats()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>仪表盘</h1>
      <p>欢迎使用AI图片智能重命名和分类工具</p>
    </div>

    <!-- 统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <div
        v-for="(card, index) in statCards"
        :key="index"
        class="stat-card"
        :style="{
          '--start-color': card.startColor,
          '--end-color': card.endColor,
          '--color-rgb': card.rgb
        }"
      >
        <div class="flex justify-between items-start">
          <div>
            <div class="stat-number">{{ card.value }}</div>
            <div class="stat-label">{{ card.title }}</div>
          </div>
          <component :is="card.icon" size="36" style="opacity: 0.9" />
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- 快速操作 -->
      <div class="card lg:col-span-1">
        <h3 class="text-xl font-bold mb-6">快速操作</h3>
        <el-button type="primary" size="large" @click="goToProcess" class="w-full mb-4">
          <el-icon class="mr-2"><Picture /></el-icon>
          开始处理图片
        </el-button>
        <el-button type="default" size="large" @click="getStats" class="w-full mb-4">
          <el-icon class="mr-2"><Refresh /></el-icon>
          刷新统计
        </el-button>
        <el-button type="default" size="large" @click="$router.push('/tasks')" class="w-full">
          <el-icon class="mr-2"><List /></el-icon>
          查看任务
        </el-button>
      </div>

      <!-- 分类分布图表 -->
      <div class="card lg:col-span-2">
        <h3 class="text-xl font-bold mb-6">分类分布</h3>
        <v-chart :option="chartOption" class="h-80" autoresize />
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
}

.gap-6 {
  gap: 24px;
}

.mb-8 {
  margin-bottom: 32px;
}

.mb-4 {
  margin-bottom: 16px;
}

.text-lg {
  font-size: 18px;
}

.font-bold {
  font-weight: bold;
}

.w-full {
  width: 100%;
}

.h-80 {
  height: 320px;
}

@media (min-width: 768px) {
  .md\:grid-cols-2 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1024px) {
  .lg\:grid-cols-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .lg\:grid-cols-4 {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .lg\:col-span-1 {
    grid-column: span 1 / span 1;
  }
  .lg\:col-span-2 {
    grid-column: span 2 / span 2;
  }
}

.flex {
  display: flex;
}

.justify-between {
  justify-content: space-between;
}

.items-start {
  align-items: flex-start;
}
</style>
