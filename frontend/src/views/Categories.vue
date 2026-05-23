<script setup>
import { ref, onMounted, computed } from 'vue'
import request from '../utils/request'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, FolderOpened, ArrowLeft, Edit, Switch, Delete, View } from '@element-plus/icons-vue'

const categories = ref([])
const activeCategory = ref(null)
const files = ref([])
const loadingFiles = ref(false)

// 动态分类管理模式
const configMode = ref(false)
const categoryConfig = ref({
  categories: [],
  legacy_categories: [],
  category_keywords: {}
})
const loadingConfig = ref(false)
const savingConfig = ref(false)
const aiLoading = ref(false)

// 限制展示数量，避免一次性渲染大量图片导致卡顿
const visibleLimit = ref(100)
const visibleFiles = computed(() => {
  return files.value.slice(0, visibleLimit.value)
})

// Lightbox 大图预览状态
const showLightbox = ref(false)
const activeFileIndex = ref(-1)

// 编辑/对话框状态
const renameDialogVisible = ref(false)
const renameForm = ref({
  path: '',
  oldName: '',
  newName: ''
})

const moveDialogVisible = ref(false)
const moveForm = ref({
  path: '',
  targetCategory: ''
})

// 获取所有分类
const getCategories = async () => {
  try {
    const data = await request.get('/categories')
    categories.value = data
  } catch (error) {
    const defaultCats = [
      '人像写真', '风景自然', '插画绘画', '艺术风格', 'AI生成',
      '学习资料', '好词好句', '聊天记录', '影视动漫', '海报设计',
      '表情包梗图', '动物萌宠', '美食生活', '软件界面', '横屏',
      '1比1', '照片', '其他'
    ]
    categories.value = defaultCats.map((name, idx) => ({
      name,
      priority: name === '横屏' || name === '1比1' ? 0 : 1,
      id: idx + 1
    }))
  }
}

// 获取分类下的所有文件
const loadCategoryFiles = async (catName) => {
  activeCategory.value = catName
  loadingFiles.value = true
  files.value = []
  visibleLimit.value = 100 // 重置限制数量
  try {
    const data = await request.get(`/categories/${encodeURIComponent(catName)}/files`)
    files.value = data
  } catch (error) {
    ElMessage.error('加载分类图片失败: ' + (error.message || '未知错误'))
  } finally {
    loadingFiles.value = false
  }
}

// 返回主网格
const goBack = () => {
  activeCategory.value = null
  files.value = []
  visibleLimit.value = 100 // 重置限制数量
}

// 开启分类配置模式
const openConfigMode = async () => {
  configMode.value = true
  loadingConfig.value = true
  try {
    const data = await request.get('/categories/config')
    // 确保所有分类在 category_keywords 中都有对象，防止 v-model 报错
    if (data && data.categories) {
      if (!data.category_keywords) data.category_keywords = {}
      data.categories.forEach(cat => {
        if (!data.category_keywords[cat]) {
          data.category_keywords[cat] = { keywords: [], filename_hints: [] }
        }
      })
    }
    categoryConfig.value = data
  } catch (error) {
    ElMessage.error('获取分类配置失败: ' + (error.message || '未知错误'))
  } finally {
    loadingConfig.value = false
  }
}

const exitConfigMode = () => {
  configMode.value = false
  getCategories() // 重新加载分类列表
}

const saveCategoryConfig = async () => {
  savingConfig.value = true
  try {
    await request.post('/categories/config', categoryConfig.value)
    ElMessage.success('分类配置保存成功')
  } catch (error) {
    ElMessage.error('保存分类配置失败: ' + (error.message || '未知错误'))
  } finally {
    savingConfig.value = false
  }
}

const callAIAssist = async (catName) => {
  if (!catName) return
  aiLoading.value = true
  try {
    const data = await request.post('/ai_assist/optimize', { category_name: catName })
    if (!categoryConfig.value.category_keywords[catName]) {
      categoryConfig.value.category_keywords[catName] = { keywords: [], filename_hints: [] }
    }
    categoryConfig.value.category_keywords[catName].keywords = data.keywords || []
    categoryConfig.value.category_keywords[catName].filename_hints = data.filename_hints || []
    ElMessage.success(`AI 已成功生成【${catName}】的关键词`)
  } catch (error) {
    ElMessage.error('AI 生成失败: ' + (error.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

const addNewCategory = () => {
  ElMessageBox.prompt('请输入新分类名称', '添加分类', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  }).then(({ value }) => {
    if (value && !categoryConfig.value.categories.includes(value)) {
      categoryConfig.value.categories.push(value)
      categoryConfig.value.category_keywords[value] = { keywords: [], filename_hints: [] }
    }
  }).catch(() => {})
}

const handleCatNameChange = (oldName, newName, idx) => {
  if (oldName !== newName) {
    // 迁移数据
    if (categoryConfig.value.category_keywords[oldName]) {
      categoryConfig.value.category_keywords[newName] = { ...categoryConfig.value.category_keywords[oldName] }
      delete categoryConfig.value.category_keywords[oldName]
    } else {
      categoryConfig.value.category_keywords[newName] = { keywords: [], filename_hints: [] }
    }
  }
}

const removeCategory = (idx) => {
  const catName = categoryConfig.value.categories[idx]
  categoryConfig.value.categories.splice(idx, 1)
  delete categoryConfig.value.category_keywords[catName]
}

// 打开 Lightbox 大图预览
const openLightbox = (visibleIdx) => {
  const targetFile = visibleFiles.value[visibleIdx]
  const fullIdx = files.value.findIndex(f => f.path === targetFile.path)
  activeFileIndex.value = fullIdx !== -1 ? fullIdx : 0
  showLightbox.value = true
}

// 关闭 Lightbox
const closeLightbox = () => {
  showLightbox.value = false
}

// 幻灯片左右切换
const prevImage = () => {
  if (activeFileIndex.value > 0) {
    activeFileIndex.value--
  } else {
    activeFileIndex.value = files.value.length - 1
  }
}

const nextImage = () => {
  if (activeFileIndex.value < files.value.length - 1) {
    activeFileIndex.value++
  } else {
    activeFileIndex.value = 0
  }
}

// 处理重命名
const openRenameDialog = (file) => {
  renameForm.value = {
    path: file.path,
    oldName: file.name,
    newName: file.name
  }
  renameDialogVisible.value = true
}

const executeRename = async () => {
  if (!renameForm.value.newName.trim()) {
    ElMessage.warning('请输入新文件名')
    return
  }
  try {
    const res = await request.post('/image/rename', {
      image_path: renameForm.value.path,
      new_name: renameForm.value.newName
    })
    ElMessage.success('重命名成功')
    
    // 更新本地列表中的文件数据
    const idx = files.value.findIndex(f => f.path === renameForm.value.path)
    if (idx !== -1) {
      files.value[idx].name = res.new_name
      files.value[idx].path = res.new_path
      files.value[idx].relative_path = res.relative_path
    }
    renameDialogVisible.value = false
  } catch (error) {
    ElMessage.error('重命名失败: ' + (error.message || '未知错误'))
  }
}

// 处理重新分类 (移动)
const openMoveDialog = (file) => {
  moveForm.value = {
    path: file.path,
    targetCategory: activeCategory.value
  }
  moveDialogVisible.value = true
}

const executeMove = async () => {
  if (!moveForm.value.targetCategory || moveForm.value.targetCategory === activeCategory.value) {
    ElMessage.warning('请选择其他分类目录')
    return
  }
  try {
    await request.post('/image/move', {
      image_path: moveForm.value.path,
      target_category: moveForm.value.targetCategory
    })
    ElMessage.success('成功移动到分类 ' + moveForm.value.targetCategory)
    
    // 从当前分类文件列表中淡出移除该图
    files.value = files.value.filter(f => f.path !== moveForm.value.path)
    moveDialogVisible.value = false
  } catch (error) {
    ElMessage.error('移动分类失败: ' + (error.message || '未知错误'))
  }
}

// 处理物理删除
const handleDeleteImage = async (file) => {
  try {
    await request.delete('/image', {
      data: { image_path: file.path }
    })
    ElMessage.success('图片已成功物理删除')
    // 列表移除
    files.value = files.value.filter(f => f.path !== file.path)
  } catch (error) {
    ElMessage.error('删除图片失败: ' + (error.message || '未知错误'))
  }
}

onMounted(() => {
  getCategories()
})
</script>

<template>
  <div class="categories-view">
    <!-- 双视图头部 -->
    <div class="page-header flex justify-between items-center">
      <div>
        <h1 class="flex items-center gap-2">
          <el-icon v-if="activeCategory || configMode" @click="configMode ? exitConfigMode() : goBack()" class="cursor-pointer back-icon"><ArrowLeft /></el-icon>
          <span>{{ configMode ? '管理分类定义' : (activeCategory ? `分类管理 - ${activeCategory}` : '分类管理') }}</span>
        </h1>
        <p>{{ configMode ? '自定义分类、关键词、以及AI识别特征' : (activeCategory ? `查看并操作该目录下的图片（支持手动命名、重新归档和安全删除）` : '管理18个语义分类目录与比例图片资产') }}</p>
      </div>
      <div>
        <el-button v-if="!activeCategory && !configMode" type="primary" class="morandi-btn" @click="openConfigMode">
          <el-icon class="mr-1"><Edit /></el-icon> 定义新分类
        </el-button>
        <el-button v-if="activeCategory" type="default" @click="goBack" class="morandi-btn">
          <el-icon class="mr-1"><ArrowLeft /></el-icon> 返回分类列表
        </el-button>
        <el-button v-if="configMode" type="default" @click="exitConfigMode" class="morandi-btn">
          <el-icon class="mr-1"><ArrowLeft /></el-icon> 返回
        </el-button>
      </div>
    </div>

    <!-- 视图0：分类定义配置 -->
    <Transition name="fade" mode="out-in">
      <div v-if="configMode" class="card">
        <div v-if="loadingConfig" class="flex justify-center p-10"><el-skeleton animated /></div>
        <div v-else>
          <div class="mb-4 flex justify-between">
            <el-button type="primary" @click="addNewCategory">
              <el-icon class="mr-1"><Plus /></el-icon> 添加新分类
            </el-button>
            <el-button type="success" :loading="savingConfig" @click="saveCategoryConfig">
              保存配置
            </el-button>
          </div>
          
          <div class="custom-table mt-4">
            <div class="custom-table-header">
              <div class="col-name">分类名称</div>
              <div class="col-keywords">判定关键词 (用逗号分隔)</div>
              <div class="col-hints">文件名特征 (用逗号分隔)</div>
              <div class="col-actions">操作</div>
            </div>
            <div class="custom-table-body">
              <div v-for="(cat, idx) in categoryConfig.categories" :key="idx" class="custom-table-row">
                <div class="col-name">
                  <el-input v-model="categoryConfig.categories[idx]" @change="handleCatNameChange(cat, categoryConfig.categories[idx], idx)" />
                </div>
                <div class="col-keywords">
                  <el-input 
                    v-model="categoryConfig.category_keywords[categoryConfig.categories[idx]].keywords"
                    :formatter="(val) => Array.isArray(val) ? val.join(', ') : val"
                    :parser="(val) => val.split(',').map(s => s.trim()).filter(Boolean)"
                    type="textarea" :rows="2"
                    placeholder="例如: 风景, 树木, 天空"
                  />
                </div>
                <div class="col-hints">
                  <el-input 
                    v-model="categoryConfig.category_keywords[categoryConfig.categories[idx]].filename_hints"
                    :formatter="(val) => Array.isArray(val) ? val.join(', ') : val"
                    :parser="(val) => val.split(',').map(s => s.trim()).filter(Boolean)"
                    type="textarea" :rows="2"
                    placeholder="例如: img_, scr_"
                  />
                </div>
                <div class="col-actions">
                  <el-button size="small" type="warning" plain @click="callAIAssist(categoryConfig.categories[idx])" :loading="aiLoading">
                    ✨ AI完善
                  </el-button>
                  <el-button size="small" type="danger" circle @click="removeCategory(idx)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 视图1：主分类网格 -->
      <div v-else-if="!activeCategory" class="card">
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          <div
            v-for="cat in categories"
            :key="cat.name"
            class="cat-card cursor-pointer"
            :class="{ 'high-priority': cat.priority === 0 }"
            @click="loadCategoryFiles(cat.name)"
          >
            <div class="flex justify-between items-start mb-4">
              <div class="w-10 h-10 rounded-xl flex items-center justify-center icon-wrapper">
                <el-icon size="20"><FolderOpened /></el-icon>
              </div>
              <el-tag v-if="cat.priority === 0" type="danger" size="small" effect="dark" class="priority-tag">高优先级</el-tag>
            </div>
            <h3 class="cat-name">{{ cat.name }}</h3>
            <p class="cat-desc opacity-70 text-xs">点击进入文件库预览操作</p>
          </div>
        </div>
      </div>

      <!-- 视图2：图片网格浏览器 -->
      <div v-else class="card category-browser">
        <div v-if="loadingFiles" class="flex flex-col items-center justify-center p-20 loading-wrapper">
          <el-skeleton :rows="6" animated />
        </div>
        
        <div v-else-if="files.length === 0" class="flex flex-col items-center justify-center p-20 empty-wrapper">
          <el-empty description="当前分类目录下没有任何图片资源" />
        </div>

        <div v-else>
          <div class="browser-stats mb-6 text-sm flex justify-between items-center">
            <span>当前分类共收集到 <strong class="text-accent">{{ files.length }}</strong> 张图片</span>
            <span class="opacity-60">点击图片即可全屏高清预览</span>
          </div>

          <!-- 瀑布流/自适应图片网格 -->
          <div class="photo-grid">
            <TransitionGroup name="list">
              <div
                v-for="(file, idx) in visibleFiles"
                :key="file.path"
                class="image-card"
              >
                <!-- 预览图容器 -->
                <div class="image-wrapper cursor-pointer" @click="openLightbox(idx)">
                  <img :src="`/images/${file.relative_path}`" :alt="file.name" loading="lazy" />
                  <div class="hover-mask flex items-center justify-center">
                    <el-icon size="28" color="white"><View /></el-icon>
                  </div>
                </div>

                <!-- 底部操作区 -->
                <div class="card-details p-4">
                  <div class="file-name" :title="file.name">{{ file.name }}</div>
                  <div class="file-meta flex justify-between text-xs opacity-60 mt-1 mb-3">
                    <span>{{ file.size }} KB</span>
                    <span>{{ new Date(file.mtime * 1000).toLocaleDateString() }}</span>
                  </div>

                  <div class="action-bar flex gap-2">
                    <el-button size="small" type="primary" class="flex-1" @click.stop="openRenameDialog(file)">
                      <el-icon class="mr-1"><Edit /></el-icon> 重命名
                    </el-button>
                    <el-button size="small" type="default" class="flex-1" @click.stop="openMoveDialog(file)">
                      <el-icon class="mr-1"><Switch /></el-icon> 移动
                    </el-button>
                    
                    <el-popconfirm
                      title="确定要物理删除该图片吗？此操作不可逆！"
                      confirm-button-text="确定删除"
                      cancel-button-text="取消"
                      confirm-button-type="danger"
                      @confirm="handleDeleteImage(file)"
                    >
                      <template #reference>
                        <el-button size="small" type="danger" circle>
                          <el-icon><Delete /></el-icon>
                        </el-button>
                      </template>
                    </el-popconfirm>
                  </div>
                </div>
              </div>
            </TransitionGroup>
          </div>

          <!-- 加载更多按钮 -->
          <div v-if="files.length > visibleLimit" class="load-more-container">
            <el-button type="primary" size="large" class="morandi-btn px-8" @click="visibleLimit += 100">
              展开更多 (已展示 {{ visibleFiles.length }} / {{ files.length }} 张)
            </el-button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 重命名对话框 -->
    <el-dialog v-model="renameDialogVisible" title="手动重命名图片" width="500px" align-center class="morandi-dialog">
      <el-form label-width="80px">
        <el-form-item label="当前名称">
          <el-input v-model="renameForm.oldName" disabled />
        </el-form-item>
        <el-form-item label="新文件名">
          <el-input v-model="renameForm.newName" placeholder="请输入新文件名，后缀自动保留" autofocus />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="renameDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="executeRename">保存修改</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 移动分类对话框 -->
    <el-dialog v-model="moveDialogVisible" title="安全迁移图片分类" width="460px" align-center class="morandi-dialog">
      <div class="mb-4 text-sm opacity-80">将该图片从 【{{ activeCategory }}】 移动至其他归档目录下：</div>
      <el-form label-width="80px">
        <el-form-item label="目标分类">
          <el-select v-model="moveForm.targetCategory" placeholder="请选择新分类目录" class="w-full">
            <el-option
              v-for="cat in categories"
              :key="cat.name"
              :label="cat.name"
              :value="cat.name"
              :disabled="cat.name === activeCategory"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="moveDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="executeMove">确认移动</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Lightbox 全屏预览大图 -->
    <div v-if="showLightbox" class="lightbox-overlay" @click.self="closeLightbox">
      <div class="lightbox-close" @click="closeLightbox">&times;</div>
      
      <div class="lightbox-nav prev" @click="prevImage">&lt;</div>
      <div class="lightbox-content">
        <img :src="`/images/${files[activeFileIndex]?.relative_path}`" :alt="files[activeFileIndex]?.name" />
        <div class="lightbox-caption">{{ files[activeFileIndex]?.name }} ({{ files[activeFileIndex]?.size }} KB)</div>
      </div>
      <div class="lightbox-nav next" @click="nextImage">&gt;</div>
    </div>
  </div>
</template>

<style scoped>
.categories-view {
  width: 100%;
}

.back-icon {
  transition: transform 0.2s;
  padding: 4px;
  border-radius: 8px;
}
.back-icon:hover {
  transform: scale(1.1);
  background: var(--progress-bg);
}

.grid {
  display: grid;
}

.cat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 20px;
  padding: 24px;
  box-shadow: 0 4px 16px var(--shadow-color);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
}

.cat-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 12px 32px var(--shadow-color);
  border-color: rgba(199, 177, 152, 0.4);
}

.cat-card.high-priority {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.08) 100%);
  border-color: rgba(102, 126, 234, 0.2);
}

.cat-card.high-priority:hover {
  border-color: rgba(102, 126, 234, 0.5);
  box-shadow: 0 12px 32px rgba(102, 126, 234, 0.15);
}

.icon-wrapper {
  background: var(--progress-bg);
  color: var(--accent-primary);
}

.priority-tag {
  border-radius: 8px;
}

.cat-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.cat-desc {
  color: var(--text-secondary);
}

.category-browser {
  min-height: 400px;
}

.text-accent {
  color: var(--accent-primary);
  font-size: 16px;
}

/* 图片卡片样式 */
.image-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 4px 16px var(--shadow-color);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
}

.image-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 16px 36px var(--shadow-color);
  border-color: rgba(199, 177, 152, 0.35);
}

.image-wrapper {
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  position: relative;
  background: var(--preview-bg, #000);
}

.image-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s;
}

.image-card:hover .image-wrapper img {
  transform: scale(1.08);
}

.hover-mask {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.4);
  opacity: 0;
  transition: opacity 0.3s;
}

.image-wrapper:hover .hover-mask {
  opacity: 1;
}

.file-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  color: var(--text-secondary);
}

/* 动画效果 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.list-move,
.list-enter-active,
.list-leave-active {
  transition: all 0.4s cubic-bezier(0.55, 0, 0.1, 1);
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: scale(0.9);
}
.list-leave-active {
  position: absolute;
}

/* Lightbox 大图预览 */
.lightbox-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.92);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-content {
  max-width: 85%;
  max-height: 85%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.lightbox-content img {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
  box-shadow: 0 10px 50px rgba(0,0,0,0.5);
  border-radius: 8px;
}

.lightbox-caption {
  color: white;
  margin-top: 15px;
  font-size: 15px;
  background: rgba(0,0,0,0.6);
  padding: 6px 16px;
  border-radius: 20px;
}

.lightbox-close {
  position: absolute;
  top: 30px;
  right: 40px;
  color: var(--text-secondary);
  font-size: 40px;
  cursor: pointer;
  transition: color 0.2s;
}
.lightbox-close:hover {
  color: var(--text-primary);
}

.lightbox-nav {
  position: absolute;
  color: var(--text-secondary);
  font-size: 48px;
  cursor: pointer;
  user-select: none;
  padding: 20px;
  transition: color 0.2s;
}
.lightbox-nav:hover {
  color: var(--text-primary);
}
.lightbox-nav.prev {
  left: 30px;
}
.lightbox-nav.next {
  right: 30px;
}

.w-full {
  width: 100%;
}

.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 24px;
}

.load-more-container {
  display: flex;
  justify-content: center;
  margin-top: 32px;
  margin-bottom: 16px;
}

/* Custom Table Styles */
.custom-table {
  width: 100%;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
}

.custom-table-header {
  display: flex;
  background-color: var(--bg-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
  padding: 12px 16px;
}

.custom-table-row {
  display: flex;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}
.custom-table-row:last-child {
  border-bottom: none;
}

.col-name { width: 150px; padding-right: 16px; }
.col-keywords { flex: 1; padding-right: 16px; }
.col-hints { flex: 1; padding-right: 16px; }
.col-actions { width: 180px; display: flex; gap: 8px; justify-content: center; align-items: center; }
</style>
