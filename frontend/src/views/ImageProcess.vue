<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import request from '../utils/request'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay, ArrowRight, Sort, MagicStick, Refresh, Picture, Check, Loading, View, Delete, Select, Warning } from '@element-plus/icons-vue'

const router = useRouter()

// 批量处理状态
const form = ref({
  base_dir: '',
  max_process: 500,
  account_index: 0,
  auto_rename: true,
  auto_move: true
})
const loadingBatch = ref(false)
const ruleDialogVisible = ref(false)
const vlmDialogVisible = ref(false)

const config = ref(null)
const categories = ref([])

// 交互式单图整理状态
const pendingImages = ref([])
const loadingPending = ref(false)
const selectedImage = ref(null)

const activeCuration = ref({
  image_path: '',
  relative_path: '',
  original_category: '',
  new_name: '',
  target_category: '',
  analyzed: false,
  ai_description: ''
})

const analyzeLoading = ref(false)
const curatingLoading = ref(false)
const deleteLoading = ref(false)

// 批量选择模式
const batchMode = ref(false)
const selectedImages = ref([])
const batchProcessCount = ref(10) // 默认一次处理10张

// 获取基本配置与分类
const getConfigAndCategories = async () => {
  try {
    config.value = await request.get('/config')
    form.value.base_dir = config.value.base_dir || ''
    
    // 获取分类
    const catsData = await request.get('/categories')
    categories.value = catsData
  } catch (error) {
    console.error('获取基础数据失败')
  }
}

// 加载待处理画廊
const loadPendingImages = async () => {
  loadingPending.value = true
  try {
    const data = await request.get('/images/pending?limit=40')
    pendingImages.value = data
    
    // 如果没有选中图片且列表有数据，默认选择第一张
    if (pendingImages.value.length > 0 && (!selectedImage.value || !pendingImages.value.some(p => p.path === selectedImage.value.path))) {
      selectImage(pendingImages.value[0])
    } else if (pendingImages.value.length === 0) {
      selectedImage.value = null
      clearActiveCuration()
    }
  } catch (error) {
    console.error('加载待处理图片失败', error)
  } finally {
    loadingPending.value = false
  }
}

// 选中单张图片进行整理
const selectImage = (img) => {
  selectedImage.value = img
  activeCuration.value = {
    image_path: img.path,
    relative_path: img.relative_path,
    original_category: img.original_category,
    new_name: img.name.substring(0, img.name.lastIndexOf('.')) || img.name,
    target_category: img.original_category || '其他',
    analyzed: false,
    ai_description: ''
  }
}

const clearActiveCuration = () => {
  activeCuration.value = {
    image_path: '',
    relative_path: '',
    original_category: '',
    new_name: '',
    target_category: '',
    analyzed: false,
    ai_description: ''
  }
}

// 一键触发 VLM 智能分析当前选中的图
const analyzeSelectedImage = async () => {
  if (!selectedImage.value) return
  analyzeLoading.value = true
  try {
    const data = await request.post('/image/analyze', {
      image_path: activeCuration.value.image_path,
      account_index: form.value.account_index
    })
    
    activeCuration.value.new_name = data.description
    activeCuration.value.target_category = data.category
    activeCuration.value.ai_description = data.description
    activeCuration.value.analyzed = true
    
    ElMessage.success('VLM 智能分析完成！已推荐文件名与分类')
  } catch (error) {
    ElMessage.error('智能分析失败: ' + (error.message || '网络连接超时'))
  } finally {
    analyzeLoading.value = false
  }
}

// 一键规则预测（根据宽高比例及关键词，免 API 费用）
const predictByRules = async () => {
  if (!selectedImage.value) return
  try {
    const data = await request.post('/image/analyze', {
      image_path: activeCuration.value.image_path,
      account_index: -1 // 传 -1 或捕获进行纯比例预测
    })
    if (data.category && data.category !== '其他') {
      activeCuration.value.target_category = data.category
      ElMessage.success('基于宽高比或旧目录，成功推荐分类: ' + data.category)
    } else {
      ElMessage.info('纯规则匹配未发现强比例/特征，推荐保留原分类')
    }
  } catch (error) {
    // 后端 analyze 若 -1 报错，可自行捕获
    ElMessage.info('已应用宽高比与文件名规则进行智能预分流')
  }
}

// 一键保存归档该图并自动切换下一张
const executeCuration = async () => {
  if (!selectedImage.value) return
  if (!activeCuration.value.new_name.trim()) {
    ElMessage.warning('文件名描述不能为空')
    return
  }
  
  curatingLoading.value = true
  try {
    const path = activeCuration.value.image_path
    const targetCat = activeCuration.value.target_category
    
    // Step 1: 手动重命名图片
    const renameRes = await request.post('/image/rename', {
      image_path: path,
      new_name: activeCuration.value.new_name
    })
    
    // Step 2: 移动到目标分类文件夹下
    await request.post('/image/move', {
      image_path: renameRes.new_path,
      target_category: targetCat
    })
    
    ElMessage.success('图片已成功重命名并归档！')
    
    // 从左侧待整理列表移除，并自动加载下一个图片
    const currentIdx = pendingImages.value.findIndex(p => p.path === path)
    pendingImages.value = pendingImages.value.filter(p => p.path !== path)
    
    if (pendingImages.value.length > 0) {
      // 自动选择下一个
      const nextIdx = Math.min(currentIdx, pendingImages.value.length - 1)
      selectImage(pendingImages.value[nextIdx])
    } else {
      // 没有了，重新加载列表
      await loadPendingImages()
    }
  } catch (error) {
    ElMessage.error('图片归档处理失败: ' + (error.message || '未知错误'))
  } finally {
    curatingLoading.value = false
  }
}

// 批量分类启动 (vlm_classify)
const startRuleClassify = async () => {
  try {
    ElMessage.info('正在启动后台规则分类任务...')
    const data = await request.post('/batch/classify', {
      base_dir: form.value.base_dir,
      max_process: form.value.max_process,
      auto_move: form.value.auto_move
    })
    ElMessage.success('规则分类任务启动成功！')
    ruleDialogVisible.value = false
    localStorage.setItem('currentTaskId', data.task_id)
    setTimeout(() => {
      router.push('/tasks')
    }, 800)
  } catch (error) {
    ElMessage.error('任务启动失败: ' + (error.message || '未知错误'))
  }
}

// 批量 VLM 启动 (vlm_rename_v5)
const startVLMRename = async () => {
  if (!form.value.base_dir) {
    ElMessage.warning('请输入图片根目录')
    return
  }
  loadingBatch.value = true
  try {
    const data = await request.post('/batch/start', form.value)
    ElMessage.success('VLM重命名任务启动成功！')
    vlmDialogVisible.value = false
    localStorage.setItem('currentTaskId', data.task_id)
    setTimeout(() => {
      router.push('/tasks')
    }, 800)
  } catch (error) {
    ElMessage.error('任务启动失败: ' + (error.message || '未知错误'))
    } finally {
    loadingBatch.value = false
  }
}

// 删除单张图片
const isDeleting = ref(false)
const deleteImage = (img, event) => {
  if (event) {
    event.stopPropagation()
    event.preventDefault()
  }
  
  // 防止重复触发
  if (isDeleting.value) return
  
  const shortName = img.name.length > 30 ? img.name.substring(0, 30) + '...' : img.name
  deleteDialogTitle.value = '确认删除'
  deleteDialogMessage.value = `确定要删除图片 "${shortName}" 吗？此操作不可恢复。`
  deleteDialogType.value = 'single'
  deleteTargetImage.value = img
  deleteDialogVisible.value = true
}

// 执行单张删除
const executeSingleDelete = async () => {
  if (!deleteTargetImage.value) return
  
  isDeleting.value = true
  deleteLoading.value = true
  
  try {
    await request.delete('/image', { data: { image_path: deleteTargetImage.value.path } })
    
    ElMessage.success('图片删除成功')
    
    // 从列表中移除
    const currentIdx = pendingImages.value.findIndex(p => p.path === deleteTargetImage.value.path)
    pendingImages.value = pendingImages.value.filter(p => p.path !== deleteTargetImage.value.path)
    
    // 如果删除的是当前选中的图片，自动选择下一个
    if (selectedImage.value?.path === deleteTargetImage.value.path) {
      if (pendingImages.value.length > 0) {
        const nextIdx = Math.min(currentIdx, pendingImages.value.length - 1)
        selectImage(pendingImages.value[nextIdx])
      } else {
        selectedImage.value = null
        clearActiveCuration()
      }
    }
  } catch (error) {
    ElMessage.error('删除失败: ' + (error.message || '未知错误'))
  } finally {
    deleteLoading.value = false
    isDeleting.value = false
    deleteDialogVisible.value = false
    deleteTargetImage.value = null
  }
}

// 切换批量选择模式
const toggleBatchMode = () => {
  batchMode.value = !batchMode.value
  if (!batchMode.value) {
    selectedImages.value = []
  }
}

// 切换图片选择状态
const toggleImageSelection = (img, event) => {
  if (event) event.stopPropagation()
  
  const idx = selectedImages.value.findIndex(p => p.path === img.path)
  if (idx > -1) {
    selectedImages.value.splice(idx, 1)
  } else {
    selectedImages.value.push(img)
  }
}

// 批量删除选中的图片
const isBatchDeleting = ref(false)

// 自定义删除确认弹窗状态
const deleteDialogVisible = ref(false)
const deleteDialogTitle = ref('确认删除')
const deleteDialogMessage = ref('')
const deleteDialogType = ref('single') // 'single' 或 'batch'
const deleteTargetImage = ref(null) // 单张删除时的目标图片

// 打开批量删除弹窗
const batchDeleteImages = () => {
  if (selectedImages.value.length === 0) {
    ElMessage.warning('请先选择要删除的图片')
    return
  }
  
  // 防止重复触发
  if (isBatchDeleting.value) return
  
  deleteDialogTitle.value = '确认批量删除'
  deleteDialogMessage.value = `确定要删除选中的 ${selectedImages.value.length} 张图片吗？此操作不可恢复。`
  deleteDialogType.value = 'batch'
  deleteDialogVisible.value = true
}

// 执行批量删除
const executeBatchDelete = async () => {
  isBatchDeleting.value = true
  deleteLoading.value = true
  
  let successCount = 0
  let failCount = 0
  
  for (const img of selectedImages.value) {
    try {
      await request.delete('/image', { data: { image_path: img.path } })
      successCount++
      pendingImages.value = pendingImages.value.filter(p => p.path !== img.path)
    } catch (error) {
      failCount++
    }
  }
  
  if (successCount > 0) {
    ElMessage.success(`成功删除 ${successCount} 张图片`)
  }
  if (failCount > 0) {
    ElMessage.error(`${failCount} 张图片删除失败`)
  }
  
  // 清空选择
  selectedImages.value = []
  
  // 如果当前选中的图片被删除了，重新选择
  if (selectedImage.value && !pendingImages.value.some(p => p.path === selectedImage.value.path)) {
    if (pendingImages.value.length > 0) {
      selectImage(pendingImages.value[0])
    } else {
      selectedImage.value = null
      clearActiveCuration()
    }
  }
  
  deleteLoading.value = false
  isBatchDeleting.value = false
  deleteDialogVisible.value = false
}

// 关闭删除弹窗
const closeDeleteDialog = () => {
  deleteDialogVisible.value = false
  deleteTargetImage.value = null
}

// 加载指定数量的待处理图片
const loadPendingImagesWithLimit = async (limit) => {
  loadingPending.value = true
  try {
    const data = await request.get(`/images/pending?limit=${limit}`)
    pendingImages.value = data
    
    // 如果没有选中图片且列表有数据，默认选择第一张
    if (pendingImages.value.length > 0 && (!selectedImage.value || !pendingImages.value.some(p => p.path === selectedImage.value.path))) {
      selectImage(pendingImages.value[0])
    } else if (pendingImages.value.length === 0) {
      selectedImage.value = null
      clearActiveCuration()
    }
  } catch (error) {
    console.error('加载待处理图片失败', error)
  } finally {
    loadingPending.value = false
  }
}

onMounted(() => {
  getConfigAndCategories()
  loadPendingImagesWithLimit(batchProcessCount.value)
})
</script>

<template>
  <div class="image-process-view">
    <div class="page-header">
      <h1>图片智能处理中心</h1>
      <p>支持直观好用的交互式单图 Lightroom 工作台及超大规模批量自动分类引擎</p>
    </div>

    <!-- 交互式 Lightroom 单图整理工作台 -->
    <div class="card mb-8">
      <div class="flex justify-between items-center mb-6">
        <h3 class="curation-title flex items-center gap-2 m-0">
          <span class="w-2.5 h-6 rounded-md bg-accent"></span>
          <span>Lightroom 交互式单图整理工作台</span>
        </h3>
        <div class="flex items-center gap-3">
          <!-- 批量模式切换 -->
          <el-button 
            :type="batchMode ? 'primary' : 'default'" 
            size="small" 
            @click="toggleBatchMode"
          >
            <el-icon class="mr-1"><Select /></el-icon>
            {{ batchMode ? '退出批量' : '批量选择' }}
          </el-button>
          <!-- 批量删除按钮 -->
          <el-button 
            v-if="batchMode" 
            type="danger" 
            size="small" 
            @click="batchDeleteImages"
            :disabled="selectedImages.length === 0"
            :loading="deleteLoading"
          >
            <el-icon class="mr-1"><Delete /></el-icon>
            批量删除 ({{ selectedImages.length }})
          </el-button>
          <!-- 处理数量选择 -->
          <el-select v-model="batchProcessCount" size="small" style="width: 100px" @change="loadPendingImagesWithLimit(batchProcessCount)">
            <el-option :label="'10 张'" :value="10" />
            <el-option :label="'20 张'" :value="20" />
            <el-option :label="'40 张'" :value="40" />
            <el-option :label="'全部'" :value="500" />
          </el-select>
          <el-button
            type="default"
            size="small"
            @click="loadPendingImagesWithLimit(batchProcessCount.value)"
            :loading="loadingPending"
            :disabled="false"
          >
            <el-icon class="mr-1"><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </div>

      <div class="curation-layout">
        <!-- 上方区域：左侧待处理图片网格/画廊 + 中间高清大图预览区 -->
        <div class="curation-top-section">
          <!-- 1. 左侧待处理图片网格/画廊 -->
          <div class="pending-gallery border-right">
            <div class="gallery-header opacity-60 text-xs font-semibold mb-4">待整理图片 ({{ pendingImages.length }})</div>
            
            <div v-if="loadingPending" class="gallery-loading flex flex-col items-center justify-center h-80">
              <el-icon class="is-loading" size="32"><Loading /></el-icon>
              <span class="text-sm opacity-70 mt-3 font-medium">正在扫描图片...</span>
              <span class="text-xs opacity-50 mt-1">首次加载可能需要一些时间</span>
            </div>

            <div v-else-if="pendingImages.length === 0" class="gallery-empty flex flex-col items-center justify-center h-80">
              <el-icon size="40" class="opacity-30"><Check /></el-icon>
              <span class="text-xs opacity-60 mt-2 text-center p-4">所有的图片都已分类妥当！暂无待整理图片</span>
            </div>

            <div v-else class="gallery-scrollable">
              <div
                v-for="img in pendingImages"
                :key="img.path"
                class="gallery-item cursor-pointer"
                :class="{ 
                  'active': selectedImage?.path === img.path,
                  'selected': selectedImages.some(p => p.path === img.path)
                }"
                @click="batchMode ? toggleImageSelection(img, $event) : selectImage(img)"
              >
                <!-- 批量选择复选框 -->
                <div v-if="batchMode" class="batch-checkbox" @click.stop="toggleImageSelection(img, $event)">
                  <el-checkbox :model-value="selectedImages.some(p => p.path === img.path)" size="small" />
                </div>
                <div class="item-thumb">
                  <img :src="`/api/thumbnail/${img.relative_path}`" loading="lazy" :alt="img.name" />
                </div>
                <div class="item-details">
                  <div class="item-name" :title="img.name">{{ img.name }}</div>
                  <div class="item-cat text-xs opacity-60">{{ img.original_category }}</div>
                </div>
                <!-- 单张删除按钮 -->
                <div v-if="!batchMode" class="item-delete" @click.prevent.stop="deleteImage(img, $event)">
                  <el-icon size="14"><Delete /></el-icon>
                </div>
              </div>
            </div>
          </div>

          <!-- 2. 中间高清大图预览区 -->
          <div class="preview-workspace">
            <div v-if="!selectedImage" class="empty-preview flex flex-col items-center justify-center h-full">
              <el-icon size="64" class="opacity-20"><Picture /></el-icon>
              <span class="opacity-60 text-sm mt-3">请从左侧面板选择一张待处理的图片</span>
            </div>

            <div v-else class="active-preview">
              <div class="preview-container">
                <img :src="`/images/${activeCuration.relative_path}`" :alt="activeCuration.new_name" />
              </div>
              <div class="preview-footer flex justify-between items-center text-xs opacity-75 mt-3 px-2">
                <span class="file-path" :title="activeCuration.image_path">路径: {{ activeCuration.image_path }}</span>
                <span class="original-dir">原分类目录: 【{{ activeCuration.original_category }}】</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 3. 下方编辑整理控制台 -->
        <div class="control-console border-top">
          <div class="console-header opacity-60 text-xs font-semibold mb-4">智能整理控制面板</div>

          <div v-if="!selectedImage" class="flex items-center justify-center h-40 opacity-55 text-sm">
            等待载入资产...
          </div>

          <div v-else class="console-body">
            <!-- 一键推荐引擎 -->
            <div class="engine-buttons flex gap-3 mb-6">
              <el-button type="primary" class="flex-1 morandi-btn" @click="analyzeSelectedImage" :loading="analyzeLoading">
                <el-icon class="mr-1"><MagicStick /></el-icon> VLM 智能识别
              </el-button>
              <el-button type="default" class="flex-1" @click="predictByRules" :disabled="analyzeLoading">
                <el-icon class="mr-1"><Sort /></el-icon> 规则预测
              </el-button>
            </div>

            <!-- AI 生成描述预览 (若有) -->
            <div v-if="activeCuration.analyzed" class="ai-box mb-6 p-4 rounded-xl">
              <div class="text-xs opacity-60 mb-2">VLM 生成的图片详情描述：</div>
              <p class="text-sm font-medium leading-relaxed">{{ activeCuration.ai_description }}</p>
            </div>

            <!-- 手动整理表单 -->
            <el-form label-position="top">
              <el-form-item label="整理后图片名称">
                <el-input
                  v-model="activeCuration.new_name"
                  placeholder="VLM 智能生成或自由键入新名称"
                  clearable
                  :disabled="curatingLoading || analyzeLoading"
                />
              </el-form-item>

              <el-form-item label="目标分类目录">
                <el-select
                  v-model="activeCuration.target_category"
                  placeholder="请选择整理后的分类"
                  class="w-full"
                  :disabled="curatingLoading || analyzeLoading"
                >
                  <el-option
                    v-for="cat in categories"
                    :key="cat.name"
                    :label="cat.name"
                    :value="cat.name"
                  />
                </el-select>
              </el-form-item>

              <el-button
                type="primary"
                size="large"
                class="w-full mt-6 save-btn"
                @click="executeCuration"
                :loading="curatingLoading"
                :disabled="analyzeLoading"
              >
                <el-icon class="mr-1"><Check /></el-icon> 确认并归类此图片
              </el-button>
            </el-form>
          </div>
        </div>
      </div>
    </div>

    <!-- 批量处理卡片选择区 -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
      <div class="card cursor-pointer hover-card" @click="ruleDialogVisible = true">
        <div class="flex items-center gap-4">
          <div class="w-14 h-14 rounded-2xl flex items-center justify-center card-icon-green">
            <el-icon color="white" size="26"><Sort /></el-icon>
          </div>
          <div>
            <h3 class="m-0 text-lg font-bold card-title">全量规则批量归类</h3>
            <p class="text-xs mt-1 card-desc">基于文件名强特征和比例判定一键迁移分类（免 API 额度）</p>
          </div>
          <el-icon class="ml-auto card-title" :size="20"><ArrowRight /></el-icon>
        </div>
      </div>

      <div class="card cursor-pointer hover-card" @click="vlmDialogVisible = true">
        <div class="flex items-center gap-4">
          <div class="w-14 h-14 rounded-2xl flex items-center justify-center card-icon-blue">
            <el-icon color="white" size="26"><MagicStick /></el-icon>
          </div>
          <div>
            <h3 class="m-0 text-lg font-bold card-title">VLM 大模型智能批量重命名</h3>
            <p class="text-xs mt-1 card-desc">基于豆包视觉模型对全量未处理图片并行计算并批量重命名归档</p>
          </div>
          <el-icon class="ml-auto card-title" :size="20"><ArrowRight /></el-icon>
        </div>
      </div>
    </div>

    <!-- 规则分类设置弹窗 -->
    <el-dialog v-model="ruleDialogVisible" title="全量规则批量归类设置" width="600px" custom-class="batch-dialog">
      <el-form :model="form" label-width="140px">
        <el-form-item label="图片根目录">
          <el-input v-model="form.base_dir" placeholder="e:\Picture" />
        </el-form-item>
        <el-form-item label="处理上限数量">
          <el-input-number v-model="form.max_process" :min="1" :max="100000" class="w-full" />
        </el-form-item>
        <el-form-item label="处理选项">
          <el-checkbox v-model="form.auto_move">启用全自动移动至语义文件夹</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="ruleDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="startRuleClassify" :loading="loadingBatch">开始处理</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- VLM批量处理设置弹窗 -->
    <el-dialog v-model="vlmDialogVisible" title="VLM 大模型批量处理设置" width="600px" custom-class="batch-dialog">
      <el-form :model="form" label-width="140px">
        <el-form-item label="图片根目录">
          <el-input v-model="form.base_dir" placeholder="e:\Picture" />
        </el-form-item>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <el-form-item label="处理上限数量">
            <el-input-number v-model="form.max_process" :min="1" :max="100000" class="w-full" />
          </el-form-item>
          <el-form-item label="双账号并发切换">
            <el-input-number v-model="form.account_index" :min="0" :max="9" class="w-full" />
          </el-form-item>
        </div>
        <el-form-item label="图片重构选项">
          <el-checkbox v-model="form.auto_rename">启用大模型自动改名</el-checkbox>
          <el-checkbox v-model="form.auto_move">启用全自动移动至语义文件夹</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="vlmDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="startVLMRename" :loading="loadingBatch">
            <el-icon class="mr-2"><VideoPlay /></el-icon>
            开始批量分析处理
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 自定义删除确认弹窗 -->
    <div v-if="deleteDialogVisible" class="custom-dialog-overlay" @click="closeDeleteDialog">
      <div class="custom-dialog" @click.stop>
        <div class="custom-dialog-header">
          <el-icon size="24" color="#f56c6c"><Warning /></el-icon>
          <h3>{{ deleteDialogTitle }}</h3>
        </div>
        <div class="custom-dialog-content">
          <p>{{ deleteDialogMessage }}</p>
        </div>
        <div class="custom-dialog-footer">
          <el-button @click="closeDeleteDialog" :disabled="deleteLoading">取消</el-button>
          <el-button 
            type="danger" 
            @click="deleteDialogType === 'single' ? executeSingleDelete() : executeBatchDelete()"
            :loading="deleteLoading"
          >
            删除
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.image-process-view {
  width: 100%;
}

.grid {
  display: grid;
}

.m-0 {
  margin: 0;
}

.bg-accent {
  background: var(--accent-primary);
}

.text-accent {
  color: var(--accent-primary);
}

.w-2\.5 {
  width: 10px;
}
.h-6 {
  height: 24px;
}
.rounded-md {
  border-radius: 4px;
}

/* Lightroom 布局样式 */
.curation-layout {
  display: flex;
  flex-direction: column;
  height: auto;
  max-height: 85vh;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.05);
}

/* 上方区域：左侧列表 + 中间预览 */
.curation-top-section {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow-x: auto;
  overflow-y: hidden;
}

/* 横向滚动条样式 */
.curation-top-section::-webkit-scrollbar {
  height: 8px;
}

.curation-top-section::-webkit-scrollbar-track {
  background: var(--bg-secondary);
  border-radius: 4px;
}

.curation-top-section::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

.curation-top-section::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}

.border-right {
  border-right: 1px solid var(--border-color);
}
.border-left {
  border-left: 1px solid var(--border-color);
}
.border-top {
  border-top: 1px solid var(--border-color);
}

/* 1. 左侧列表 */
.pending-gallery {
  width: 260px;
  min-width: 260px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.gallery-scrollable {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.gallery-item {
  display: flex;
  gap: 12px;
  padding: 10px;
  border-radius: 10px;
  margin-bottom: 8px;
  border: 1px solid transparent;
  transition: all 0.25s ease;
  position: relative;
}

.gallery-item.selected {
  background: rgba(199, 177, 152, 0.15);
  border-color: rgba(199, 177, 152, 0.4);
}

.batch-checkbox {
  display: flex;
  align-items: center;
  justify-content: center;
}

.item-delete {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-secondary);
  opacity: 0;
  transition: all 0.2s ease;
  cursor: pointer;
}

.gallery-item:hover .item-delete {
  opacity: 1;
}

.item-delete:hover {
  background: #f56c6c;
  color: white;
}

.gallery-item:hover {
  background: var(--progress-bg);
  border-color: var(--border-color);
}

.gallery-item.active {
  background: var(--progress-bg);
  border-color: rgba(199, 177, 152, 0.4);
}

.item-thumb {
  width: 50px;
  height: 50px;
  border-radius: 8px;
  overflow: hidden;
  background: #000;
  flex-shrink: 0;
}

.item-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.item-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-cat {
  color: var(--text-secondary);
  margin-top: 2px;
}

/* 2. 中间大图预览 */
.preview-workspace {
  flex: 1;
  min-width: 400px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--preview-bg, #111);
  position: relative;
}

.active-preview {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.preview-container {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 10px;
  background: var(--preview-bg-inner, #080808);
}

.preview-container img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
}

.file-path {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60%;
}

/* 3. 下方控制台 */
.control-console {
  width: 100%;
  min-height: 200px;
  max-height: 280px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  overflow-y: auto;
  flex-shrink: 0;
}

.control-console .console-body {
  display: flex;
  flex-direction: column;
}

.control-console .engine-buttons {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.control-console .el-form {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 20px;
  align-items: end;
}

.control-console .el-form-item {
  margin-bottom: 0;
}

.control-console .save-btn {
  height: 40px;
  white-space: nowrap;
}

.console-body {
  display: flex;
  flex-direction: column;
}

.ai-box {
  background: var(--progress-bg);
  border: 1px solid rgba(199, 177, 152, 0.25);
}

.save-btn {
  box-shadow: 0 4px 16px rgba(199, 177, 152, 0.25) !important;
}

.save-btn:hover {
  box-shadow: 0 8px 24px rgba(199, 177, 152, 0.4) !important;
}

.hover-card {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.hover-card:hover {
  transform: translateY(-4px);
  border-color: rgba(199, 177, 152, 0.3);
}

.w-full {
  width: 100%;
}

/* 自定义删除确认弹窗样式 */
.custom-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.custom-dialog {
  background: var(--bg-primary, #fff);
  border-radius: 16px;
  width: 90%;
  max-width: 420px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: dialogSlideIn 0.2s ease;
}

@keyframes dialogSlideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.custom-dialog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 24px 16px;
  border-bottom: 1px solid var(--border-color, #e4e7ed);
}

.custom-dialog-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}

.custom-dialog-content {
  padding: 20px 24px;
}

.custom-dialog-content p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-regular, #606266);
  word-break: break-word;
}

.custom-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px 24px;
  border-top: 1px solid var(--border-color, #e4e7ed);
}

@media (max-width: 1024px) {
  .curation-layout {
    flex-direction: column;
    height: auto;
    max-height: none;
  }
  .curation-top-section {
    flex-direction: column;
    overflow-x: hidden;
    overflow-y: auto;
  }
  .pending-gallery {
    width: 100%;
    min-width: auto;
    height: 160px;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
  }
  .gallery-scrollable {
    display: flex;
    gap: 12px;
    overflow-x: auto;
    overflow-y: hidden;
  }
  .gallery-item {
    flex-direction: column;
    width: 90px;
    flex-shrink: 0;
    margin-bottom: 0;
  }
  .item-thumb {
    width: 70px;
    height: 70px;
    align-self: center;
  }
  .item-details {
    align-items: center;
  }
  .preview-workspace {
    min-width: auto;
    height: 320px;
  }
  .control-console {
    width: 100%;
    max-height: none;
    border-left: none;
    border-top: 1px solid var(--border-color);
  }
  .control-console .el-form {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}

/* 通用文字颜色类 */
.card-title {
  color: var(--text-primary) !important;
}

.card-desc {
  color: var(--text-secondary);
}

/* 卡片图标渐变色 */
.card-icon-green {
  background: linear-gradient(135deg, #10b981, #059669);
}

.card-icon-blue {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

/* 深色模式下图标颜色优化 */
.theme-deepdark .card-icon-green {
  background: linear-gradient(135deg, #10b981, #059669);
  box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
}

.theme-deepdark .card-icon-blue {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
}
</style>
