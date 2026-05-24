<script setup>
import { ref, onMounted, reactive } from 'vue'
import request from '../utils/request'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Edit, Check, Close, Refresh, Download, FolderOpened } from '@element-plus/icons-vue'

const config = ref({
  base_dir: '',
  api_endpoint: '',
  default_model: '',
  assistant_model: 'doubao-seed-2-0-pro-260215',
  vlm_prompt_template: '',
  batch_size: 500,
  max_retries: 3,
  exclude_extensions: ['.svg'],
  accounts: []
})

const loading = ref(false)

// 预设的 API 端点模板
const endpointTemplates = [
  { label: '火山引擎 - 豆包大模型', value: 'https://ark.cn-beijing.volces.com/api/v3/chat/completions', icon: '🔥' },
  { label: '火山引擎 - ARM 架构', value: 'https://ark-cn-beijing.volcess.com/api/v3/chat/completions', icon: '🔥' },
  { label: 'OpenAI - GPT 系列', value: 'https://api.openai.com/v1/chat/completions', icon: '🤖' },
  { label: 'Azure OpenAI', value: 'https://YOUR_RESOURCE.openai.azure.com/openai/deployments/YOUR_MODEL/chat/completions', icon: '☁️' },
  { label: '自定义端点', value: '', icon: '⚙️' }
]

// 预设的模型名称
const modelTemplates = [
  { label: '豆包视觉模型 v5 (推荐处理图片)', value: 'doubao-seed-2-0-lite-260428' },
  { label: '豆包视觉模型 v5.5', value: 'doubao-seed-2-5-260428' },
  { label: '豆包 Pro (推荐AI助手)', value: 'doubao-seed-2-0-pro-260215' },
  { label: 'GPT-4o', value: 'gpt-4o' },
  { label: 'GPT-4o-mini', value: 'gpt-4o-mini' },
  { label: 'GPT-4-turbo', value: 'gpt-4-turbo' },
  { label: '自定义模型', value: '' }
]

const getConfig = async () => {
  try {
    const data = await request.get('/config')
    config.value = data
    // 确保 accounts 是数组
    if (!config.value.accounts) {
      config.value.accounts = []
    }
  } catch (error) {
    console.error('获取配置失败')
  }
}

const saveConfig = async () => {
  loading.value = true
  try {
    await request.post('/config', config.value)
    ElMessage.success('配置保存成功！部分配置可能需要刷新页面后生效。')
  } catch (error) {
    ElMessage.error('保存配置失败')
  } finally {
    loading.value = false
  }
}

const openLogsFolder = async () => {
  try {
    await request.post('/system/open_logs')
    ElMessage.success('日志文件夹已为您打开')
  } catch (error) {
    ElMessage.error('打开文件夹失败，请手动前往 AppData 查看')
  }
}

const clearCache = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要清除当前照片目录的处理记录吗？清除后，之前跳过的照片如果被移回根目录，将会重新被 AI 处理。',
      '清除记录',
      {
        confirmButtonText: '确定清除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    const res = await request.post('/system/clear_cache')
    ElMessage.success(res.msg || '缓存清除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '清除缓存失败')
    }
  }
}

const selectingFolder = ref(false)
const selectFolder = async () => {
  selectingFolder.value = true
  try {
    const res = await request.get('/select_folder')
    if (res && res.path) {
      config.value.base_dir = res.path
    }
  } catch (error) {
    ElMessage.error('无法打开文件夹选择框或未选择')
  } finally {
    selectingFolder.value = false
  }
}

// 账号管理
const editingAccount = reactive({})
const newAccount = ref({ name: '', keys: [], model: '' })

const startEditAccount = (index) => {
  editingAccount[index] = { ...config.value.accounts[index] }
}

const cancelEditAccount = (index) => {
  delete editingAccount[index]
}

const saveEditAccount = (index) => {
  config.value.accounts[index] = { ...editingAccount[index] }
  delete editingAccount[index]
  ElMessage.success('账号已更新')
}

const deleteAccount = (index) => {
  config.value.accounts.splice(index, 1)
  ElMessage.success('账号已删除')
}

const addAccount = () => {
  const newAcc = {
    name: newAccount.value.name || `账号${config.value.accounts.length + 1}`,
    keys: newAccount.value.keys.filter(k => k.trim()),
    model: newAccount.value.model
  }
  if (newAcc.keys.length === 0) {
    ElMessage.warning('请至少添加一个 API Key')
    return
  }
  config.value.accounts.push(newAcc)
  newAccount.value = { name: '', keys: [], model: '' }
  ElMessage.success('账号已添加')
}

const addKeyToNewAccount = () => {
  newAccount.value.keys.push('')
}

const removeKeyFromNewAccount = (index) => {
  newAccount.value.keys.splice(index, 1)
}

// 应用端点模板
const applyEndpointTemplate = (template) => {
  if (template.value) {
    config.value.api_endpoint = template.value
  }
}

// 应用模型模板
const applyModelTemplate = (template, target) => {
  if (template.value) {
    if (target === 'assistant') {
      config.value.assistant_model = template.value
    } else {
      config.value.default_model = template.value
    }
  }
}

const restoreDefaultPrompt = () => {
  config.value.vlm_prompt_template = `请分析这张图片，返回JSON格式：\n{"description": "简洁中文内容描述，不超过20字，适合作文件名", "category": "从以下类别选一个：{VLM_CATEGORY_LIST}"}\n注意：只返回JSON，不要其他文字。description不要包含特殊字符（/:*?"<>|）`
}

// 版本更新功能
const updateInfo = ref({
  loading: false,
  checked: false,
  current_version: '',
  latest_version: '',
  has_update: false,
  can_auto_update: false,
  release_url: '',
  release_notes: '',
  download_url: ''
})

const checkUpdate = async () => {
  updateInfo.value.loading = true
  try {
    const data = await request.get('/system/check_update')
    updateInfo.value = {
      ...updateInfo.value,
      ...data,
      checked: true
    }
    if (data.has_update) {
      ElMessage.success(`发现新版本：v${data.latest_version}`)
    } else {
      ElMessage.info('当前已是最新版本')
    }
  } catch (error) {
    ElMessage.error('检查更新失败')
  } finally {
    updateInfo.value.loading = false
  }
}

const pullUpdate = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要拉取最新版本并覆盖本地代码吗？此操作将使用 git 强制覆盖本地修改。',
      '更新提示',
      { confirmButtonText: '确认拉取', cancelButtonText: '取消', type: 'warning' }
    )
    
    updateInfo.value.loading = true
    await request.post('/system/pull_update')
    ElMessageBox.alert('代码拉取覆盖成功！请彻底关闭当前的终端黑框，然后重新双击 start.bat 启动系统以应用更新。', '更新完成', {
      type: 'success',
      confirmButtonText: '好的，我知道了'
    })
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('拉取更新失败')
    }
  } finally {
    updateInfo.value.loading = false
  }
}

const installUpdate = async () => {
  try {
    await ElMessageBox.confirm(
      '系统将在后台下载安装包，下载完成后会自动结束当前程序并静默安装。安装过程大约需要1-2分钟，期间请勿强行关闭。是否开始更新？',
      'OTA 静默更新',
      { confirmButtonText: '立即开始', cancelButtonText: '取消', type: 'warning' }
    )
    
    updateInfo.value.loading = true
    const res = await request.post('/system/install_update', { download_url: updateInfo.value.download_url })
    ElMessage.success(res.msg || '正在后台下载安装包，稍后将自动退出...')
    
    // We don't set loading=false here because the app will be killed anyway, 
    // keeping the button spinning indicates background task is running.
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('触发下载安装失败')
      updateInfo.value.loading = false
    }
  }
}

onMounted(() => {
  getConfig()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>配置中心</h1>
      <p>配置 API 密钥、VLM 模型来源和系统参数</p>
    </div>

    <!-- API 端点配置 -->
    <div class="card mb-6">
      <h3 class="card-title">
        <span class="title-icon">🌐</span>
        API 端点配置
      </h3>
      <p class="card-desc">选择或自定义 VLM 模型服务提供商</p>

      <div class="template-grid">
        <div
          v-for="template in endpointTemplates"
          :key="template.label"
          class="template-item"
          :class="{ active: config.api_endpoint === template.value && template.value }"
          @click="applyEndpointTemplate(template)"
        >
          <span class="template-icon">{{ template.icon }}</span>
          <span class="template-label">{{ template.label }}</span>
        </div>
      </div>

      <el-form-item label="自定义端点" class="mt-5">
        <el-input
          v-model="config.api_endpoint"
          placeholder="https://api.example.com/v1/chat/completions"
          clearable
        />
      </el-form-item>
    </div>

    <!-- 默认模型配置 -->
    <div class="card mb-6">
      <h3 class="card-title">
        <span class="title-icon">🤖</span>
        模型与提示词配置
      </h3>
      <p class="card-desc">分别设置处理图片和AI助手使用的模型，以及系统提示词模板</p>

      <div class="grid-2">
        <div>
          <h4>视觉处理模型 (Lite)</h4>
          <p class="card-desc" style="margin-bottom: 10px;">用于批量分析图片，推荐使用 Lite 模型以节省成本</p>
          <div class="template-grid model-grid">
            <div
              v-for="template in modelTemplates"
              :key="'v-'+template.label"
              class="template-item"
              :class="{ active: config.default_model === template.value && template.value }"
              @click="applyModelTemplate(template, 'vision')"
            >
              <span class="template-label">{{ template.label }}</span>
            </div>
          </div>
          <el-input
            v-model="config.default_model"
            placeholder="自定义处理模型"
            clearable
            class="mt-3"
          />
        </div>

        <div>
          <h4>AI 助手模型 (Pro)</h4>
          <p class="card-desc" style="margin-bottom: 10px;">用于生成分类关键词或优化提示词，推荐使用 Pro 模型</p>
          <div class="template-grid model-grid">
            <div
              v-for="template in modelTemplates"
              :key="'a-'+template.label"
              class="template-item"
              :class="{ active: config.assistant_model === template.value && template.value }"
              @click="applyModelTemplate(template, 'assistant')"
            >
              <span class="template-label">{{ template.label }}</span>
            </div>
          </div>
          <el-input
            v-model="config.assistant_model"
            placeholder="自定义助手模型"
            clearable
            class="mt-3"
          />
        </div>
      </div>

      <div class="mt-5">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h4>VLM 系统提示词模板</h4>
          <el-button size="small" @click="restoreDefaultPrompt">恢复默认</el-button>
        </div>
        <p class="card-desc" style="margin-bottom: 10px;">您可以自定义发送给视觉模型的基础提示词。请务必保留 <code>{VLM_CATEGORY_LIST}</code> 作为分类列表的占位符。</p>
        <el-input
          v-model="config.vlm_prompt_template"
          type="textarea"
          :rows="4"
          placeholder="留空则使用内置默认提示词..."
        />
      </div>
    </div>

    <!-- 账号管理 -->
    <div class="card mb-6">
      <h3 class="card-title">
        <span class="title-icon">🔑</span>
        API 密钥管理
      </h3>
      <p class="card-desc">管理多个账号的 API 密钥，支持按账号选择不同模型</p>

      <!-- 已有账号列表 -->
      <div class="accounts-list">
        <div v-for="(account, index) in config.accounts" :key="index" class="account-item">
          <template v-if="editingAccount[index]">
            <div class="account-edit">
              <el-input v-model="editingAccount[index].name" placeholder="账号名称" class="account-name-input" />
              <div class="keys-edit">
                <div v-for="(key, ki) in editingAccount[index].keys" :key="ki" class="key-row">
                  <el-input
                    v-model="editingAccount[index].keys[ki]"
                    type="password"
                    placeholder="API Key"
                    show-password
                  />
                  <el-button type="danger" @click="editingAccount[index].keys.splice(ki, 1)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <el-button size="small" @click="editingAccount[index].keys.push('')">+ 添加 Key</el-button>
              </div>
              <el-input v-model="editingAccount[index].model" placeholder="可选：覆盖默认模型" />
              <div class="account-actions">
                <el-button type="primary" @click="saveEditAccount(index)">
                  <el-icon><Check /></el-icon> 保存
                </el-button>
                <el-button @click="cancelEditAccount(index)">
                  <el-icon><Close /></el-icon> 取消
                </el-button>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="account-info">
              <div class="account-header">
                <span class="account-name">{{ account.name }}</span>
                <span v-if="account.model" class="account-model-tag">{{ account.model }}</span>
              </div>
              <div class="account-keys">
                <span class="key-count">包含 {{ account.keys.length }} 个 Key</span>
              </div>
            </div>
            <div class="account-actions">
              <el-button size="small" @click="startEditAccount(index)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button type="danger" size="small" @click="deleteAccount(index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </template>
        </div>
      </div>

      <!-- 添加新账号 -->
      <div class="add-account-section">
        <h4>添加新账号</h4>
        <el-input v-model="newAccount.name" placeholder="账号名称（如：我的OpenAI账号）" class="mb-3" />
        <div class="new-keys">
          <div v-for="(key, index) in newAccount.keys" :key="index" class="key-row">
            <el-input
              v-model="newAccount.keys[index]"
              type="password"
              placeholder="API Key"
              show-password
            />
            <el-button type="danger" @click="removeKeyFromNewAccount(index)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
          <el-button size="small" type="default" @click="addKeyToNewAccount">
            <el-icon><Plus /></el-icon> 添加 Key
          </el-button>
        </div>
        <el-input v-model="newAccount.model" placeholder="可选：为此账号指定不同模型（如：gpt-4o）" class="mt-3" />
        <el-button type="primary" class="mt-3" @click="addAccount">
          <el-icon><Plus /></el-icon> 添加账号
        </el-button>
      </div>
    </div>

    <!-- 系统设置 -->
    <div class="card mb-6">
      <h3 class="card-title">
        <span class="title-icon">⚙️</span>
        系统设置
      </h3>

      <el-form :model="config" label-width="140px" size="large">
        <el-form-item label="图片根目录">
          <div style="display: flex; gap: 10px; width: 100%;">
            <el-input v-model="config.base_dir" placeholder="e:\Picture" style="flex: 1;" />
            <el-button @click="selectFolder" :loading="selectingFolder">浏览...</el-button>
          </div>
        </el-form-item>
        <div class="grid-2">
          <el-form-item label="批次大小">
            <el-input-number v-model="config.batch_size" :min="10" :max="100000" class="w-full" />
          </el-form-item>
          <el-form-item label="最大重试次数">
            <el-input-number v-model="config.max_retries" :min="1" :max="10" class="w-full" />
          </el-form-item>
        </div>
        
        <el-collapse style="margin-top: 15px; width: 100%;">
          <el-collapse-item title="高级过滤设置 (已排除的文件类型)" name="1">
            <el-form-item label="排除后缀名" style="margin-bottom: 0;">
              <el-select
                v-model="config.exclude_extensions"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="请选择或输入要排除的后缀名 (如 .svg)"
                style="width: 100%"
              >
                <el-option label=".svg" value=".svg" />
                <el-option label=".ico" value=".ico" />
                <el-option label=".heic" value=".heic" />
              </el-select>
              <div style="width: 100%; margin-top: 5px;">
                <span style="color: var(--text-lighter); font-size: 13px;">包含以上后缀名的图片将被系统在最初扫描时直接跳过处理。按回车添加新的。</span>
              </div>
            </el-form-item>
          </el-collapse-item>
        </el-collapse>

        <el-form-item label="清理与排查" style="margin-top: 20px;">
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <el-button @click="openLogsFolder" type="info" plain>
              <el-icon class="mr-2"><FolderOpened /></el-icon> 打开数据与日志文件夹
            </el-button>
            <el-button @click="clearCache" type="warning" plain>
              <el-icon class="mr-2"><Delete /></el-icon> 清除当前目录图片处理记录
            </el-button>
          </div>
          <div style="width: 100%; margin-top: 5px;">
            <span style="color: var(--text-lighter); font-size: 13px;">如果您的文件夹结构发生改变，想让程序重新整理图片，可以点击【清除记录】来重置当前目录的记忆，照片就不会被系统跳过了。</span>
          </div>
        </el-form-item>
      </el-form>
    </div>

    <!-- 系统更新 -->
    <div class="card mb-6">
      <h3 class="card-title">
        <span class="title-icon">🚀</span>
        版本与更新
      </h3>
      <p class="card-desc">检查应用是否有新版本，并可通过一键覆盖拉取更新</p>
      
      <div class="update-section">
        <div class="version-info">
          <p v-if="!updateInfo.checked">点击检查更新获取最新版本信息</p>
          <div v-else>
            <p>当前版本：<el-tag type="info">v{{ updateInfo.current_version }}</el-tag></p>
            <p class="mt-3" v-if="updateInfo.has_update">
              最新版本：<el-tag type="success">v{{ updateInfo.latest_version }}</el-tag>
              <span class="update-badge">有新更新！</span>
            </p>
            <p class="mt-3" v-else>
              状态：<el-tag type="success">已经是最新版本</el-tag>
            </p>
            
            <div v-if="updateInfo.has_update && updateInfo.release_notes" class="release-notes mt-3">
              <h4>更新日志：</h4>
              <pre>{{ updateInfo.release_notes }}</pre>
            </div>
          </div>
        </div>
        
        <div class="update-actions mt-3">
          <el-button type="primary" @click="checkUpdate" :loading="updateInfo.loading">
            <el-icon class="mr-2"><Refresh /></el-icon> 检查更新
          </el-button>
          
          <template v-if="updateInfo.checked && updateInfo.has_update">
            <el-button 
              v-if="updateInfo.can_auto_update" 
              type="success" 
              @click="pullUpdate" 
              :loading="updateInfo.loading"
            >
              <el-icon class="mr-2"><Download /></el-icon> 一键拉取覆盖更新
            </el-button>
            <el-button 
              v-else-if="updateInfo.download_url" 
              type="success" 
              @click="installUpdate" 
              :loading="updateInfo.loading"
              style="margin-left: 12px;"
            >
              <el-icon class="mr-2"><Download /></el-icon> 自动下载并安装更新
            </el-button>
            <a 
              v-else 
              :href="updateInfo.release_url" 
              target="_blank" 
              style="margin-left: 12px; text-decoration: none;"
            >
              <el-button type="success">
                前往发布页下载最新版
              </el-button>
            </a>
          </template>
        </div>
      </div>
    </div>

    <!-- 保存按钮 -->
    <div class="save-section">
      <el-button type="primary" size="large" @click="saveConfig" :loading="loading">
        <el-icon class="mr-2"><Check /></el-icon>
        保存所有配置
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.mb-6 {
  margin-bottom: 24px;
}

.mb-3 {
  margin-bottom: 12px;
}

.mt-3 {
  margin-top: 12px;
}

.mt-5 {
  margin-top: 20px;
}

.mr-2 {
  margin-right: 8px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

.title-icon {
  font-size: 20px;
}

.card-desc {
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 20px;
}

/* 模板选择 */
.template-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.template-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.template-item:hover {
  border-color: var(--accent-primary);
  background: var(--progress-bg);
}

.template-item.active {
  border-color: var(--accent-primary);
  background: var(--progress-bg);
  box-shadow: inset 0 0 0 1px var(--accent-primary);
}

.template-icon {
  font-size: 18px;
}

.template-label {
  font-size: 14px;
  font-weight: 500;
}

/* 账号列表 */
.accounts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}

.account-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.account-info {
  flex: 1;
}

.account-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.account-name {
  font-weight: 600;
  font-size: 15px;
}

.account-model-tag {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--progress-bg);
  border-radius: 6px;
  color: var(--text-secondary);
}

.account-keys {
  font-size: 13px;
  color: var(--text-secondary);
}

.account-actions {
  display: flex;
  gap: 8px;
}

/* 账号编辑 */
.account-edit {
  width: 100%;
}

.account-edit .el-input,
.account-edit .el-select {
  margin-bottom: 10px;
}

.account-name-input {
  margin-bottom: 12px;
}

.keys-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.key-row {
  display: flex;
  gap: 8px;
}

.key-row .el-input {
  flex: 1;
}

/* 添加账号 */
.add-account-section {
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px dashed var(--border-color);
  border-radius: 12px;
}

.add-account-section h4 {
  margin-bottom: 16px;
  font-size: 15px;
  font-weight: 600;
}

.new-keys {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 网格布局 */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.w-full {
  width: 100%;
}

/* 保存按钮 */
.save-section {
  text-align: center;
  margin-top: 32px;
}

@media (max-width: 768px) {
  .grid-2 {
    grid-template-columns: 1fr;
  }

  .account-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .account-actions {
    width: 100%;
    justify-content: flex-end;
  }
}

.update-section {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.update-badge {
  color: #f56c6c;
  font-weight: bold;
  margin-left: 10px;
}

.release-notes {
  background: var(--code-bg);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  max-height: 200px;
  overflow-y: auto;
}

.release-notes pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
}
</style>
