<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'

import ArticleLibrarySection from './components/ArticleLibrarySection.vue'
import ArticleMonitoringSection from './components/ArticleMonitoringSection.vue'
import BenchmarkAccountsSection from './components/BenchmarkAccountsSection.vue'
import MicroheadlineSettingsPanel from './components/MicroheadlineSettingsPanel.vue'
import { callDesktop, hasDesktopApi, subscribeDesktopEvents } from './desktop'

const DEFAULT_SUBTITLE_SETTINGS = {
  fontSize: 42,
  styleId: 'white-teal',
  fontColor: '#FFFFFF',
  outlineColor: '#0091A8',
  outlineThick: 70
}
const DEFAULT_MODEL_SETTINGS = {
  baseUrl: '',
  apiKey: '',
  model: '',
  titlePrompt: ''
}
const DEFAULT_GLOBAL_SETTINGS = {
  threadPoolSize: 3,
  downloadDir: '',
  checkWebsiteLinks: false
}
const DEFAULT_HUASHENG_VOICE_SETTINGS = {
  voiceId: 0,
  voiceName: '',
  voiceCode: '',
  voiceTags: '',
  previewUrl: '',
  cover: '',
  speechRate: 1,
  maxConcurrentTasksPerAccount: 1
}
const DEFAULT_SUBTITLE_FONT_SIZE_OPTIONS = [
  { label: '超小号', value: 22 },
  { label: '小号', value: 32 },
  { label: '常规', value: 42 },
  { label: '大号', value: 54 }
]
const DEFAULT_SUBTITLE_STYLE_OPTIONS = [
  {
    id: 'white-black',
    label: '白字黑描边',
    fontColor: '#FFFFFF',
    outlineColor: '#000000',
    outlineThick: 70
  },
  {
    id: 'black-white',
    label: '黑字白描边',
    fontColor: '#000000',
    outlineColor: '#FFFFFF',
    outlineThick: 70
  },
  {
    id: 'yellow-black',
    label: '黄字黑描边',
    fontColor: '#FFD707',
    outlineColor: '#000000',
    outlineThick: 70
  },
  {
    id: 'white-red',
    label: '白字红描边',
    fontColor: '#FFFFFF',
    outlineColor: '#FF1A1A',
    outlineThick: 70
  },
  {
    id: 'cyan-black',
    label: '浅青黑描边',
    fontColor: '#AFE6EF',
    outlineColor: '#000000',
    outlineThick: 70
  },
  {
    id: 'white-pink',
    label: '白字粉描边',
    fontColor: '#FFFFFF',
    outlineColor: '#FF6699',
    outlineThick: 70
  },
  {
    id: 'white-teal',
    label: '白字青描边',
    fontColor: '#FFFFFF',
    outlineColor: '#0091A8',
    outlineThick: 70
  }
]

const desktopReady = ref(false)
const appVersion = ref('')
const loading = ref(false)
const saving = ref(false)
const busyAccountId = ref(null)
const activeSection = ref('accounts')
const accountDialogOpen = ref(false)
const voicePickerDialogOpen = ref(false)
const voicePickerTarget = ref('project')
const statusMessage = ref('等待 PyWebView 初始化')
const filterMode = ref('all')
const searchKeyword = ref('')
const lastSyncedAt = ref('')
const activeDebugTab = ref('tts')
const activeSettingsTab = ref('huasheng')
const visitedSections = reactive({
  accounts: true,
  tasks: false,
  benchmarkAccounts: false,
  articleMonitoring: false,
  articleLibrary: false,
  debug: false,
  settings: false
})
const visitedDebugTabs = reactive({
  tts: true,
  project: false,
  imageOcr: false,
  rewrite: false,
  title: false
})
const visitedSettingsTabs = reactive({
  global: false,
  huasheng: true,
  ocr: false,
  microheadline: false,
  model: false
})
const ttsLoading = ref(false)
const ttsSourceTab = ref('public')
const ttsPlaybackRate = ref(1)
const ttsPreviewing = ref(false)
const ttsRequest = reactive({
  pn: 1,
  ps: 50,
  categoryId: 0
})
const ttsMaterials = ref([])
const ttsCategories = ref([])
const ttsPage = ref(null)
const ttsLastUsedVoiceId = ref('')
const selectedTtsVoiceId = ref('')
const ttsLastFetchAccount = ref(null)
const ttsLastFetchAt = ref('')
const tasksLoading = ref(false)
const taskStatusDialogOpen = ref(false)
const taskDeleteDialogOpen = ref(false)
const taskDeleteLoading = ref(false)
const taskRecords = ref([])
const downloadingTaskIds = ref([])
const retryingTaskIds = ref([])
const currentProjectTaskRecordId = ref(null)
const projectLoading = ref(false)
const projectPolling = ref(false)
const projectPollCount = ref(0)
const projectSubtitleLoading = ref(false)
const projectExportLoading = ref(false)
const projectExportPolling = ref(false)
const projectExportPollCount = ref(0)
const projectLastFetchAccount = ref(null)
const projectLastFetchAt = ref('')
const projectResult = ref(null)
const projectInfo = ref(null)
const projectSubtitleResult = ref(null)
const projectExportTask = ref(null)
const projectExportInfo = ref(null)
const projectForm = reactive({
  accountId: '',
  name: '',
  script: '「花生」可以做高大上的科普视频。比如，种花生要注意什么？花生是喜温作物，适宜生长在温暖湿润、排水性好的沙质壤土中，土壤酸碱度以中性为宜。它对光照和温度要求较高，生长期需要充足光照，日均气温保持在20℃以上更利于生长发育。全球核心种植区集中在北半球温带及亚热带地区，我国山东、河南、河北是主要产区，产量占全国多数，所产花生颗粒饱满、含油率高。此外，美国东南部、印度、阿根廷等国也广泛栽培。「花生」也可以讲历史。比如，花生的原产地在什么地方？花生原产于南美洲，16世纪明代中晚期经海路传入中国，福建、广东为最早引种地。小花生因耐贫瘠、适应性强，先在东南沿海扎根，清代向北推广至山东、河南等产区。明代已有煮食、炒制吃法，清代吃法更丰富，19世纪中后期大花生成为主流，花生油走入寻常百姓家，四百年间从闲食变为餐桌必备食材。「花生」还能聊聊商业财经上的财富密码。比如，中国作为全球花生产量、消费、进口三料冠军，2024年产量近1900万吨，占全球38%，年产值稳稳站上千亿级别。全球贸易中，中国既是73.4万吨的出口大户，也是151万吨的进口主力，从原料到深加工产品形成完整产业链。消费升级下，高端食用油、健康零食持续扩容，这颗小花生正撬动大市场。「花生」是一个输入文案或口播帮你自动找素材、剪辑成片的工具。不管你是喜欢用键盘噼里啪啦敲出灵感的文字大佬，还是更爱用语音滔滔不绝表达的话痨选手，都能在花生这儿找到最丝滑的创作体验。「花生」还有超多隐藏玩法等着各位解锁！赶紧去探索吧~',
  voiceId: '',
  speechRate: 1
})
const stats = ref({
  total: 0,
  active: 0,
  disabled: 0
})
const accounts = ref([])
const databasePath = ref('')
const subtitleSettingsLoading = ref(false)
const subtitleSettingsSaving = ref(false)
const subtitleSettingsLoaded = ref(false)
const subtitleLastSavedAt = ref('')
const huashengVoiceSettingsLoading = ref(false)
const huashengVoiceSettingsSaving = ref(false)
const huashengVoiceSettingsLoaded = ref(false)
const huashengVoiceLastSavedAt = ref('')
const globalSettingsLoading = ref(false)
const globalSettingsSaving = ref(false)
const globalSettingsLoaded = ref(false)
const globalSettingsLastSavedAt = ref('')
const ocrModelStatusLoading = ref(false)
const ocrModelDownloadLoading = ref(false)
const ocrModelStatusLoaded = ref(false)
const ocrModelStatus = ref(null)
const modelSettingsLoading = ref(false)
const modelSettingsSaving = ref(false)
const modelConnectionLoading = ref(false)
const modelSettingsLoaded = ref(false)
const modelSettingsLastSavedAt = ref('')
const subtitleFontSizeOptions = ref(DEFAULT_SUBTITLE_FONT_SIZE_OPTIONS)
const subtitleStyleOptions = ref(DEFAULT_SUBTITLE_STYLE_OPTIONS)
const subtitleSettings = reactive({
  ...DEFAULT_SUBTITLE_SETTINGS
})
const huashengVoiceSettings = reactive({
  ...DEFAULT_HUASHENG_VOICE_SETTINGS
})
const globalSettings = reactive({
  ...DEFAULT_GLOBAL_SETTINGS
})
const modelSettings = reactive({
  ...DEFAULT_MODEL_SETTINGS
})
const rewritePrompts = ref([])
const persistedRewritePrompts = ref([])
const rewriteLoading = ref(false)
const rewriteConnectionLoading = ref(false)
const rewriteErrorMessage = ref('')
const rewriteResult = ref(null)
const rewriteForm = reactive({
  baseUrl: '',
  apiKey: '',
  model: '',
  promptId: '',
  article: ''
})
const titleLoading = ref(false)
const titleConnectionLoading = ref(false)
const titleErrorMessage = ref('')
const titleResult = ref(null)
const titleForm = reactive({
  baseUrl: '',
  apiKey: '',
  model: '',
  titlePrompt: '',
  article: ''
})
const imageOcrLoading = ref(false)
const imageOcrErrorMessage = ref('')
const imageOcrResult = ref(null)
const imageOcrForm = reactive({
  imagePath: ''
})
const form = reactive({
  id: null,
  phone: '',
  cookies: '',
  note: '',
  isDisabled: false
})

const PROJECT_POLL_INTERVAL_MS = 5000
const PROJECT_MAX_POLLS = 36
const PROJECT_EXPORT_POLL_INTERVAL_MS = 5000
const PROJECT_EXPORT_MAX_POLLS = 36
const TASK_LIST_REFRESH_INTERVAL_MS = 5000

const navigationItems = [
  {
    key: 'accounts',
    label: '花生账号',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`
  },
  {
    key: 'tasks',
    label: '任务列表',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>`
  },
  {
    key: 'benchmarkAccounts',
    label: '对标账号',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 11h-6"/><path d="M20 8v6"/></svg>`
  },
  {
    key: 'articleMonitoring',
    label: '文章抓取',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/></svg>`
  },
  {
    key: 'articleLibrary',
    label: '文章列表',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>`
  },
  {
    key: 'debug',
    label: '调试',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6"/><path d="M10 9V4"/><path d="M14 9V4"/><rect x="5" y="9" width="14" height="10" rx="3"/><path d="M9 13h.01"/><path d="M15 13h.01"/><path d="M8 19v2"/><path d="M16 19v2"/></svg>`
  },
  {
    key: 'settings',
    label: '设置',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`
  }
]

const debugTabs = [
  {
    key: 'tts',
    label: '音色选择',
    description: '拉取并挑选花生创作后台的 TTS 音色'
  },
  {
    key: 'project',
    label: '创建任务',
    description: '选择发布账号并发起 project/create 调试请求'
  },
  {
    key: 'imageOcr',
    label: '图片初审',
    description: '选择一张图片，用 PaddleOCR 识别其中的文字内容'
  },
  {
    key: 'rewrite',
    label: '文章改写',
    description: '使用数据库提示词调用模型改写文章'
  },
  {
    key: 'title',
    label: '标题生成',
    description: '使用标题提示词为文章生成标题'
  }
]

const settingsTabs = [
  {
    key: 'global',
    label: '全局设置',
    description: '线程池大小与后台任务扫描'
  },
  {
    key: 'huasheng',
    label: '花生设置',
    description: '字幕字号、字幕样式和默认音色'
  },
  {
    key: 'ocr',
    label: 'OCR 设置',
    description: '检查模型状态并下载本地 OCR 模型'
  },
  {
    key: 'model',
    label: '模型设置',
    description: 'Base URL、API Key、Model 和提示词'
  },
  {
    key: 'microheadline',
    label: '微头条设置',
    description: '抓取自动化与默认筛选门槛'
  }
]

const isEditing = computed(() => form.id !== null)
const filteredAccounts = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()

  return accounts.value.filter((account) => {
    if (filterMode.value === 'enabled' && account.isDisabled) {
      return false
    }
    if (filterMode.value === 'disabled' && !account.isDisabled) {
      return false
    }
    if (!keyword) {
      return true
    }

    return [account.phone, account.note, account.cookies]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(keyword))
  })
})

const debugAccountPool = computed(() => {
  const enabledAccounts = accounts.value.filter((account) => !account.isDisabled)
  return enabledAccounts.length ? enabledAccounts : accounts.value
})

const selectedProjectAccount = computed(() => {
  return accounts.value.find((account) => String(account.id) === String(projectForm.accountId)) ?? null
})

const projectBusy = computed(() => {
  return (
    projectLoading.value ||
    projectPolling.value ||
    projectSubtitleLoading.value ||
    projectExportLoading.value ||
    projectExportPolling.value
  )
})

const canCreateProject = computed(() => {
  return (
    desktopReady.value &&
    Boolean(selectedProjectAccount.value?.cookies?.trim()) &&
    Number(projectForm.voiceId) > 0 &&
    !projectBusy.value
  )
})

const projectValidationMessage = computed(() => {
  if (!desktopReady.value) {
    return '当前不在 PyWebView 环境内'
  }
  if (projectBusy.value) {
    return '任务正在处理中，请等待完成'
  }
  if (!selectedProjectAccount.value?.cookies?.trim()) {
    return '请先选择发布账号'
  }
  if (Number(projectForm.voiceId) <= 0) {
    return '请先点击选择音色'
  }
  return '参数已就绪，可以创建任务'
})

const projectPayload = computed(() => projectInfo.value?.project ?? null)

const projectProgressValue = computed(() => {
  const value = Number(projectPayload.value?.progress ?? 0)
  return Number.isFinite(value) ? value : 0
})

const projectStateText = computed(() => {
  return projectPayload.value?.state_message || projectPayload.value?.loading_msg || '等待创建'
})

const projectDisplayId = computed(() => {
  return projectPayload.value?.id || projectResult.value?.id || '--'
})

const projectDisplayPid = computed(() => {
  return projectPayload.value?.pid || projectResult.value?.pid || '--'
})

const projectExportTaskId = computed(() => {
  return projectExportTask.value?.task_id || '--'
})

const projectExportVersion = computed(() => {
  return projectExportTask.value?.version || '--'
})

const projectExportProgressValue = computed(() => {
  const value = Number(projectExportInfo.value?.progress ?? 0)
  return Number.isFinite(value) ? value : 0
})

const projectExportUrl = computed(() => {
  const url = projectExportInfo.value?.url
  return typeof url === 'string' ? url.trim() : ''
})

const projectExportStateText = computed(() => {
  if (!projectExportTask.value?.task_id) {
    return '未开始导出'
  }
  if (projectExportUrl.value && projectExportProgressValue.value >= 100) {
    return '导出完成'
  }
  if (projectExportPolling.value || projectExportLoading.value) {
    return `导出中 ${projectExportProgressValue.value}%`
  }
  return `导出进度 ${projectExportProgressValue.value}%`
})

const projectViewUrl = computed(() => {
  return projectExportUrl.value
})

const projectCanView = computed(() => {
  return projectExportProgressValue.value >= 100 && Boolean(projectExportUrl.value)
})

const projectIsFinished = computed(() => {
  if (!projectResult.value?.pid && projectDisplayPid.value === '--') {
    return false
  }

  return isProjectFinished(projectInfo.value ?? { project: projectPayload.value })
})

const projectCanExport = computed(() => {
  return (
    desktopReady.value &&
    Boolean(selectedProjectAccount.value?.cookies?.trim()) &&
    Number(projectDisplayId.value) > 0 &&
    String(projectDisplayPid.value) !== '--' &&
    !projectBusy.value
  )
})

const projectCurrentStageLabel = computed(() => {
  if (projectLoading.value) {
    return '创建中...'
  }
  if (projectPolling.value) {
    return '处理中'
  }
  if (projectSubtitleLoading.value) {
    return '设置字幕'
  }
  if (projectExportLoading.value) {
    return '发起导出'
  }
  if (projectExportPolling.value) {
    return '导出中'
  }
  if (projectCanView.value) {
    return '可查看'
  }
  if (projectExportTask.value?.task_id) {
    return '导出待完成'
  }
  if (projectIsFinished.value) {
    return '可导出'
  }
  if (canCreateProject.value) {
    return '可以创建'
  }
  return '等待补全参数'
})

const projectStatusSummary = computed(() => {
  if (projectBusy.value) {
    return statusMessage.value
  }
  if (projectCanView.value) {
    return '导出完成，可直接查看成片'
  }
  if (projectExportTask.value?.task_id) {
    return projectExportStateText.value
  }
  if (projectIsFinished.value) {
    return '项目处理完成，可点击导出按钮'
  }
  if (projectResult.value?.pid) {
    return projectStateText.value
  }
  return projectValidationMessage.value
})

const selectedTtsVoice = computed(() => {
  return (
    ttsMaterials.value.find((voice) => String(voice.id) === String(selectedTtsVoiceId.value)) ??
    null
  )
})

const ttsCategoryOptions = computed(() => {
  const items = [{ id: 0, title: '全部' }]
  const seen = new Set([0])

  function appendCategories(categories) {
    for (const category of categories ?? []) {
      const children = Array.isArray(category.children) ? category.children : []
      if (children.length) {
        appendCategories(category.children)
        continue
      }

      const id = Number(category.id)
      if (Number.isFinite(id) && !seen.has(id) && category.title) {
        seen.add(id)
        items.push({
          id,
          title: category.title
        })
      }
    }
  }

  appendCategories(ttsCategories.value)
  return items
})

const ttsSelectedVoiceLabel = computed(() => {
  if (!selectedTtsVoice.value) {
    return '尚未选择音色'
  }

  return `${selectedTtsVoice.value.name} · ${getVoiceTags(selectedTtsVoice.value)}`
})

const selectedSubtitleStyle = computed(() => {
  return (
    subtitleStyleOptions.value.find((item) => item.id === subtitleSettings.styleId) ?? null
  )
})

const subtitleSettingsSummary = computed(() => {
  const sizeLabel =
    subtitleFontSizeOptions.value.find((item) => item.value === subtitleSettings.fontSize)?.label ||
    `${subtitleSettings.fontSize}`
  const styleLabel = selectedSubtitleStyle.value?.label || '未选择样式'
  return `${sizeLabel} · ${styleLabel}`
})

const huashengVoiceSummary = computed(() => {
  const concurrentLabel = `单账号并发 ${normalizeHuashengMaxConcurrentTasks(
    huashengVoiceSettings.maxConcurrentTasksPerAccount
  )}`
  if (Number(huashengVoiceSettings.voiceId) <= 0 || !huashengVoiceSettings.voiceName) {
    return `未设置默认音色 · ${concurrentLabel}`
  }

  return `${huashengVoiceSettings.voiceName} · ${Number(huashengVoiceSettings.speechRate || 1).toFixed(1)}x · ${concurrentLabel}`
})

const globalSettingsSummary = computed(() => {
  const downloadLabel = globalSettings.downloadDir ? '已设置下载目录' : '未设置下载目录'
  const websiteCheckLabel = normalizeGlobalCheckWebsiteLinks(globalSettings.checkWebsiteLinks)
    ? '网址审核开启'
    : '网址审核关闭'
  return `线程池 ${Number(globalSettings.threadPoolSize || DEFAULT_GLOBAL_SETTINGS.threadPoolSize)} 个线程 · ${downloadLabel} · ${websiteCheckLabel}`
})

const ocrModelSummary = computed(() => {
  if (!ocrModelStatus.value) {
    return '尚未检查 OCR 模型状态'
  }

  return String(ocrModelStatus.value.message || '').trim() || 'OCR 状态未知'
})

const displayAppVersion = computed(() => {
  const normalized = String(appVersion.value || '').trim()
  return normalized ? `v${normalized}` : '待连接'
})

const voicePickerTitle = computed(() => {
  return voicePickerTarget.value === 'settings' ? '设置默认音色' : '选择音色'
})

const voicePickerCaption = computed(() => {
  return voicePickerTarget.value === 'settings' ? '花生设置' : '花生调试台'
})

const voicePickerDescription = computed(() => {
  return voicePickerTarget.value === 'settings'
    ? '点击卡片选中音色，可先试听，确认后会把音色和语速一起保存到数据库。'
    : '点击卡片选中音色，可先试听，再带回创建任务表单。'
})

const voicePickerApplyLabel = computed(() => {
  return voicePickerTarget.value === 'settings' ? '保存音色设置' : '使用当前音色'
})

const rewritePromptCount = computed(() => {
  return rewritePrompts.value.length
})

const persistedRewritePromptCount = computed(() => {
  return persistedRewritePrompts.value.length
})

const selectedRewritePrompt = computed(() => {
  return (
    persistedRewritePrompts.value.find(
      (item) => String(item.id) === String(rewriteForm.promptId || '')
    ) ?? null
  )
})

const imageOcrFileName = computed(() => {
  return getPathTail(imageOcrForm.imagePath)
})

const taskCount = computed(() => {
  return taskRecords.value.length
})

const taskStatusCounts = computed(() => {
  return buildTaskStatusSummaryItems(taskRecords.value, (task) => getTaskDisplayStatus(task))
})

const taskHuashengStatusCounts = computed(() => {
  return buildTaskStatusSummaryItems(taskRecords.value, (task) => task.huashengStatus)
})

let unsubscribeDesktopEvents = null
let previewAudio = null
let projectPollingToken = 0
let rewritePromptSeed = 0
let taskListAutoRefreshHandle = null

function nextRewritePromptId() {
  rewritePromptSeed += 1
  return `prompt-${Date.now()}-${rewritePromptSeed}`
}

function setActiveSection(section) {
  if (section && Object.prototype.hasOwnProperty.call(visitedSections, section)) {
    visitedSections[section] = true
  }
  activeSection.value = section
}

function setActiveDebugTab(tabKey) {
  if (tabKey && Object.prototype.hasOwnProperty.call(visitedDebugTabs, tabKey)) {
    visitedDebugTabs[tabKey] = true
  }
  activeDebugTab.value = tabKey
}

function setActiveSettingsTab(tabKey) {
  if (tabKey && Object.prototype.hasOwnProperty.call(visitedSettingsTabs, tabKey)) {
    visitedSettingsTabs[tabKey] = true
  }
  activeSettingsTab.value = tabKey
}

function switchSection(section) {
  setActiveSection(section)
  if (section !== 'accounts') {
    accountDialogOpen.value = false
    resetForm()
  }
  if (section !== 'tasks') {
    taskStatusDialogOpen.value = false
  }
  if (section !== 'debug') {
    closeVoicePicker()
    stopProjectPolling()
  }
  if (
    section === 'debug' &&
    desktopReady.value &&
    !ttsMaterials.value.length &&
    !ttsLoading.value
  ) {
    fetchTtsVoices('公共音色已载入')
  }
  if (section === 'tasks' && desktopReady.value && !tasksLoading.value) {
    loadTasks('任务列表已载入')
  }
  if (
    section === 'settings' &&
    desktopReady.value &&
    !subtitleSettingsLoading.value &&
    !huashengVoiceSettingsLoading.value &&
    !globalSettingsLoading.value &&
    !modelSettingsLoading.value
  ) {
    if (!globalSettingsLoaded.value) {
      loadGlobalSettings('全局设置已载入')
    }
    if (!subtitleSettingsLoaded.value) {
      loadSubtitleSettings('字幕设置已载入')
    }
    if (!huashengVoiceSettingsLoaded.value) {
      loadHuashengVoiceSettings('音色设置已载入')
    }
    if (!modelSettingsLoaded.value) {
      loadModelSettings('模型设置已载入')
    }
  }
}

function activateDebugTab(tabKey) {
  setActiveDebugTab(tabKey)
  if (tabKey === 'project' && selectedTtsVoiceId.value) {
    projectForm.voiceId = Number(selectedTtsVoiceId.value)
  }
  if ((tabKey === 'rewrite' || tabKey === 'title') && desktopReady.value) {
    if (!modelSettingsLoaded.value && !modelSettingsLoading.value) {
      loadModelSettings('模型设置已载入到调试台')
    } else {
      syncAiDebugForms()
    }
  }
}

function activateSettingsTab(tabKey) {
  setActiveSettingsTab(tabKey)
  if (tabKey === 'global' && desktopReady.value && !globalSettingsLoaded.value) {
    loadGlobalSettings('全局设置已载入')
  }
  if (tabKey === 'huasheng' && desktopReady.value && !subtitleSettingsLoaded.value) {
    loadSubtitleSettings('字幕设置已载入')
  }
  if (tabKey === 'huasheng' && desktopReady.value && !huashengVoiceSettingsLoaded.value) {
    loadHuashengVoiceSettings('音色设置已载入')
  }
  if (tabKey === 'ocr' && desktopReady.value && !ocrModelStatusLoaded.value) {
    loadOcrModelStatus('OCR 模型状态已载入')
  }
  if (tabKey === 'model' && desktopReady.value && !modelSettingsLoaded.value) {
    loadModelSettings('模型设置已载入')
  }
}

function resetForm() {
  form.id = null
  form.phone = ''
  form.cookies = ''
  form.note = ''
  form.isDisabled = false
}

function openCreateAccountDialog() {
  setActiveSection('accounts')
  resetForm()
  accountDialogOpen.value = true
  statusMessage.value = '准备新增账号'
}

function closeAccountDialog() {
  accountDialogOpen.value = false
  resetForm()
}

function closeVoicePicker() {
  voicePickerDialogOpen.value = false
  voicePickerTarget.value = 'project'
  stopVoicePreview()
}

function openTaskStatusDialog() {
  taskStatusDialogOpen.value = true
}

function closeTaskStatusDialog() {
  taskStatusDialogOpen.value = false
}

function openTaskDeleteDialog() {
  if (!taskCount.value) {
    statusMessage.value = '当前没有可删除的任务'
    return
  }
  taskDeleteDialogOpen.value = true
}

function closeTaskDeleteDialog() {
  if (taskDeleteLoading.value) {
    return
  }
  taskDeleteDialogOpen.value = false
}

function isTaskDownloading(taskId) {
  return downloadingTaskIds.value.includes(Number(taskId) || 0)
}

function isTaskRetrying(taskId) {
  return retryingTaskIds.value.includes(Number(taskId) || 0)
}

function setTaskDownloading(taskId, downloading) {
  const normalizedTaskId = Number(taskId) || 0
  if (normalizedTaskId <= 0) {
    return
  }

  if (downloading) {
    if (!downloadingTaskIds.value.includes(normalizedTaskId)) {
      downloadingTaskIds.value = [...downloadingTaskIds.value, normalizedTaskId]
    }
    return
  }

  downloadingTaskIds.value = downloadingTaskIds.value.filter((item) => item !== normalizedTaskId)
}

function setTaskRetrying(taskId, retrying) {
  const normalizedTaskId = Number(taskId) || 0
  if (normalizedTaskId <= 0) {
    return
  }

  if (retrying) {
    if (!retryingTaskIds.value.includes(normalizedTaskId)) {
      retryingTaskIds.value = [...retryingTaskIds.value, normalizedTaskId]
    }
    return
  }

  retryingTaskIds.value = retryingTaskIds.value.filter((item) => item !== normalizedTaskId)
}

function isTaskRetryable(task) {
  const status = String(task?.status || '').trim()
  return ['S1失败', 'S2失败', 'S3失败', 'S4失败'].includes(status)
}

function stopProjectPolling() {
  projectPollingToken += 1
  projectPolling.value = false
  projectSubtitleLoading.value = false
  projectExportLoading.value = false
  projectExportPolling.value = false
}

function startTaskListAutoRefresh() {
  if (taskListAutoRefreshHandle !== null) {
    return
  }

  taskListAutoRefreshHandle = window.setInterval(() => {
    if (
      activeSection.value === 'tasks' &&
      desktopReady.value &&
      !tasksLoading.value
    ) {
      loadTasks('任务列表已自动刷新', { silent: true })
    }
  }, TASK_LIST_REFRESH_INTERVAL_MS)
}

function stopTaskListAutoRefresh() {
  if (taskListAutoRefreshHandle === null) {
    return
  }

  window.clearInterval(taskListAutoRefreshHandle)
  taskListAutoRefreshHandle = null
}

function getSubtitleStyleById(styleId) {
  return subtitleStyleOptions.value.find((item) => item.id === String(styleId || '')) ?? null
}

function resolveSubtitleSettings(rawSettings) {
  const style =
    getSubtitleStyleById(rawSettings?.styleId) ||
    subtitleStyleOptions.value.find(
      (item) =>
        item.fontColor === rawSettings?.fontColor &&
        item.outlineColor === rawSettings?.outlineColor &&
        Number(item.outlineThick) === Number(rawSettings?.outlineThick)
    ) ||
    getSubtitleStyleById(DEFAULT_SUBTITLE_SETTINGS.styleId) ||
    DEFAULT_SUBTITLE_STYLE_OPTIONS[0]

  const fontSize = Number(rawSettings?.fontSize)
  const normalizedFontSize = subtitleFontSizeOptions.value.some(
    (item) => Number(item.value) === fontSize
  )
    ? fontSize
    : DEFAULT_SUBTITLE_SETTINGS.fontSize

  return {
    fontSize: normalizedFontSize,
    styleId: style.id,
    fontColor: style.fontColor,
    outlineColor: style.outlineColor,
    outlineThick: Number(style.outlineThick) || DEFAULT_SUBTITLE_SETTINGS.outlineThick
  }
}

function resolveHuashengVoiceSettings(rawSettings) {
  const voiceId = Number(rawSettings?.voiceId) || 0
  const speechRate = Number(rawSettings?.speechRate)

  return {
    voiceId: voiceId > 0 ? voiceId : 0,
    voiceName: String(rawSettings?.voiceName || ''),
    voiceCode: String(rawSettings?.voiceCode || ''),
    voiceTags: String(rawSettings?.voiceTags || ''),
    previewUrl: String(rawSettings?.previewUrl || ''),
    cover: String(rawSettings?.cover || ''),
    speechRate:
      Number.isFinite(speechRate) && speechRate >= 0.5 && speechRate <= 2
        ? Number(speechRate.toFixed(1))
        : DEFAULT_HUASHENG_VOICE_SETTINGS.speechRate,
    maxConcurrentTasksPerAccount: normalizeHuashengMaxConcurrentTasks(
      rawSettings?.maxConcurrentTasksPerAccount
    )
  }
}

function applySubtitleSettingsPayload(payload) {
  if (Array.isArray(payload?.fontSizeOptions) && payload.fontSizeOptions.length) {
    subtitleFontSizeOptions.value = payload.fontSizeOptions
  }
  if (Array.isArray(payload?.styleOptions) && payload.styleOptions.length) {
    subtitleStyleOptions.value = payload.styleOptions
  }

  const settings = resolveSubtitleSettings(payload?.settings || subtitleSettings)
  subtitleSettings.fontSize = settings.fontSize
  subtitleSettings.styleId = settings.styleId
  subtitleSettings.fontColor = settings.fontColor
  subtitleSettings.outlineColor = settings.outlineColor
  subtitleSettings.outlineThick = settings.outlineThick
  subtitleSettingsLoaded.value = true
  subtitleLastSavedAt.value = String(payload?.updatedAt || '')

  if (payload?.databasePath) {
    databasePath.value = payload.databasePath
  }
}

function applyHuashengVoiceSettingsPayload(payload) {
  const settings = resolveHuashengVoiceSettings(payload?.settings || huashengVoiceSettings)
  huashengVoiceSettings.voiceId = settings.voiceId
  huashengVoiceSettings.voiceName = settings.voiceName
  huashengVoiceSettings.voiceCode = settings.voiceCode
  huashengVoiceSettings.voiceTags = settings.voiceTags
  huashengVoiceSettings.previewUrl = settings.previewUrl
  huashengVoiceSettings.cover = settings.cover
  huashengVoiceSettings.speechRate = settings.speechRate
  huashengVoiceSettings.maxConcurrentTasksPerAccount = settings.maxConcurrentTasksPerAccount
  huashengVoiceSettingsLoaded.value = true
  huashengVoiceLastSavedAt.value = String(payload?.updatedAt || '')

  const shouldHydrateProjectVoice = !projectForm.voiceId && settings.voiceId > 0
  if (shouldHydrateProjectVoice) {
    projectForm.voiceId = settings.voiceId
    projectForm.speechRate = settings.speechRate
  }
  if (!selectedTtsVoiceId.value && settings.voiceId > 0) {
    selectedTtsVoiceId.value = String(settings.voiceId)
  }
  if (
    !shouldHydrateProjectVoice &&
    Number(projectForm.speechRate || 0) <= 0 &&
    Number(settings.speechRate || 0) > 0
  ) {
    projectForm.speechRate = settings.speechRate
  }

  if (payload?.databasePath) {
    databasePath.value = payload.databasePath
  }
}

function selectSubtitleFontSize(option) {
  subtitleSettings.fontSize = Number(option?.value) || DEFAULT_SUBTITLE_SETTINGS.fontSize
  statusMessage.value = `已选择字幕字号 ${option?.label || subtitleSettings.fontSize}`
}

function selectSubtitleStyle(style) {
  if (!style) {
    return
  }

  subtitleSettings.styleId = style.id
  subtitleSettings.fontColor = style.fontColor
  subtitleSettings.outlineColor = style.outlineColor
  subtitleSettings.outlineThick = Number(style.outlineThick) || 70
  statusMessage.value = `已选择字幕样式 ${style.label}`
}

function createRewritePromptItem(content = '', id = null) {
  return {
    id: id ?? nextRewritePromptId(),
    content
  }
}

function normalizeGlobalThreadPoolSize(value) {
  const normalized = Number(value)
  if (!Number.isFinite(normalized)) {
    return DEFAULT_GLOBAL_SETTINGS.threadPoolSize
  }
  return Math.max(1, Math.min(32, Math.round(normalized)))
}

function normalizeGlobalDownloadDir(value) {
  return String(value || '').trim()
}

function normalizeGlobalCheckWebsiteLinks(value) {
  if (typeof value === 'boolean') {
    return value
  }

  const normalized = String(value ?? '').trim().toLowerCase()
  if (!normalized) {
    return DEFAULT_GLOBAL_SETTINGS.checkWebsiteLinks
  }
  if (['1', 'true', 'yes', 'y', 'on', '是', '开', '开启'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'n', 'off', '否', '关', '关闭'].includes(normalized)) {
    return false
  }
  return DEFAULT_GLOBAL_SETTINGS.checkWebsiteLinks
}

function normalizeHuashengMaxConcurrentTasks(value) {
  const normalized = Number(value)
  if (!Number.isFinite(normalized)) {
    return DEFAULT_HUASHENG_VOICE_SETTINGS.maxConcurrentTasksPerAccount
  }
  return Math.max(1, Math.min(50, Math.round(normalized)))
}

function getPathTail(path) {
  const normalized = normalizeGlobalDownloadDir(path)
  if (!normalized) {
    return '未设置'
  }

  const segments = normalized.split(/[\\/]/).filter(Boolean)
  return segments[segments.length - 1] || normalized
}

function getModelParameterValidationMessage(baseUrl, apiKey, model) {
  if (!String(baseUrl || '').trim() || !String(apiKey || '').trim() || !String(model || '').trim()) {
    return '请先补全 Base URL、API Key 和 Model'
  }
  return ''
}

function getModelActionMessage(payload, fallback) {
  const message = String(payload?.errorMessage || payload?.message || '').trim()
  return message || fallback
}

function getModelConnectionSuccessMessage(payload) {
  const responseText = String(payload?.responseText || '').trim()
  if (!responseText) {
    return '模型连接测试成功'
  }
  return `模型连接测试成功：${responseText.length > 80 ? `${responseText.slice(0, 80)}…` : responseText}`
}

function syncAiDebugForms({ force = false } = {}) {
  const firstPersistedPromptId = persistedRewritePrompts.value[0]?.id

  if (force || !rewriteForm.baseUrl.trim()) {
    rewriteForm.baseUrl = modelSettings.baseUrl
  }
  if (force || !rewriteForm.apiKey.trim()) {
    rewriteForm.apiKey = modelSettings.apiKey
  }
  if (force || !rewriteForm.model.trim()) {
    rewriteForm.model = modelSettings.model
  }
  if (force || !rewriteForm.promptId) {
    rewriteForm.promptId = firstPersistedPromptId ? String(firstPersistedPromptId) : ''
  }

  if (force || !titleForm.baseUrl.trim()) {
    titleForm.baseUrl = modelSettings.baseUrl
  }
  if (force || !titleForm.apiKey.trim()) {
    titleForm.apiKey = modelSettings.apiKey
  }
  if (force || !titleForm.model.trim()) {
    titleForm.model = modelSettings.model
  }
  if (force || !titleForm.titlePrompt.trim()) {
    titleForm.titlePrompt = modelSettings.titlePrompt
  }
}

function fillRewriteFormFromModelSettings() {
  syncAiDebugForms({ force: true })
  statusMessage.value = '已带入模型设置到文章改写调试台'
}

function fillTitleFormFromModelSettings() {
  syncAiDebugForms({ force: true })
  statusMessage.value = '已带入模型设置到标题生成调试台'
}

function selectRewritePrompt(prompt) {
  if (!prompt?.id) {
    return
  }
  rewriteForm.promptId = String(prompt.id)
  statusMessage.value = `已选择改写提示词 #${prompt.id}`
}

function applyModelSettingsPayload(payload) {
  const settings = payload?.settings || {}
  modelSettings.baseUrl = String(settings.baseUrl || '')
  modelSettings.apiKey = String(settings.apiKey || '')
  modelSettings.model = String(settings.model || '')
  modelSettings.titlePrompt = String(settings.titlePrompt || '')
  rewritePrompts.value = Array.isArray(payload?.prompts)
    ? payload.prompts.map((item) => createRewritePromptItem(item.content, item.id))
    : []
  persistedRewritePrompts.value = Array.isArray(payload?.prompts)
    ? payload.prompts.map((item) => ({
        id: item.id,
        content: item.content
      }))
    : []
  modelSettingsLoaded.value = true
  modelSettingsLastSavedAt.value = String(payload?.updatedAt || '')
  syncAiDebugForms()

  if (payload?.databasePath) {
    databasePath.value = payload.databasePath
  }
}

function applyGlobalSettingsPayload(payload) {
  const settings = payload?.settings || {}
  globalSettings.threadPoolSize = normalizeGlobalThreadPoolSize(settings.threadPoolSize)
  globalSettings.downloadDir = normalizeGlobalDownloadDir(settings.downloadDir)
  globalSettings.checkWebsiteLinks = normalizeGlobalCheckWebsiteLinks(settings.checkWebsiteLinks)
  globalSettingsLoaded.value = true
  globalSettingsLastSavedAt.value = String(payload?.updatedAt || '')

  if (payload?.databasePath) {
    databasePath.value = payload.databasePath
  }
}

function applyOcrModelStatusPayload(payload) {
  ocrModelStatus.value = {
    engine: String(payload?.engine || 'PaddleOCR'),
    status: String(payload?.status || ''),
    ready: Boolean(payload?.ready),
    message: String(payload?.message || ''),
    dependenciesReady: Boolean(payload?.dependenciesReady),
    dependencyItems: Array.isArray(payload?.dependencyItems) ? payload.dependencyItems : [],
    cacheDir: String(payload?.cacheDir || ''),
    cacheExists: Boolean(payload?.cacheExists),
    cacheWritable: Boolean(payload?.cacheWritable),
    cacheWritableMessage: String(payload?.cacheWritableMessage || ''),
    artifactFileCount: Number(payload?.artifactFileCount || 0),
    artifactDirectoryCount: Number(payload?.artifactDirectoryCount || 0),
    cacheSizeBytes: Number(payload?.cacheSizeBytes || 0),
    sampleFiles: Array.isArray(payload?.sampleFiles) ? payload.sampleFiles : [],
    engineInitialized: Boolean(payload?.engineInitialized),
    verified: Boolean(payload?.verified),
    verifiedAt: String(payload?.verifiedAt || '')
  }
  ocrModelStatusLoaded.value = true

  if (payload?.databasePath) {
    databasePath.value = payload.databasePath
  }
}

function applyAppStatePayload(payload) {
  appVersion.value = String(payload?.version || '').trim()
}

async function loadAppState() {
  if (!desktopReady.value) {
    return null
  }

  try {
    const payload = await callDesktop('get_app_state')
    applyAppStatePayload(payload)
    return payload
  } catch {
    appVersion.value = ''
    return null
  }
}

async function loadGlobalSettings(message = '全局设置已载入') {
  if (!desktopReady.value) {
    return null
  }

  globalSettingsLoading.value = true

  try {
    const payload = await callDesktop('get_global_settings')
    applyGlobalSettingsPayload(payload)
    statusMessage.value = `${message} · ${globalSettingsSummary.value}`
    return payload
  } catch (error) {
    globalSettingsLoaded.value = false
    statusMessage.value = `加载全局设置失败: ${error instanceof Error ? error.message : String(error)}`
    return null
  } finally {
    globalSettingsLoading.value = false
  }
}

async function saveGlobalSettings() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  globalSettingsSaving.value = true

  try {
    const payload = await callDesktop(
      'save_global_settings',
      normalizeGlobalThreadPoolSize(globalSettings.threadPoolSize),
      normalizeGlobalDownloadDir(globalSettings.downloadDir),
      normalizeGlobalCheckWebsiteLinks(globalSettings.checkWebsiteLinks)
    )
    applyGlobalSettingsPayload(payload)
    statusMessage.value = `全局设置已保存到数据库 · ${globalSettingsSummary.value}`
  } catch (error) {
    statusMessage.value = `保存全局设置失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    globalSettingsSaving.value = false
  }
}

async function loadOcrModelStatus(message = 'OCR 模型状态已载入') {
  if (!desktopReady.value) {
    return null
  }

  ocrModelStatusLoading.value = true

  try {
    const payload = await callDesktop('get_ocr_model_status')
    if (!payload?.success) {
      throw new Error(payload?.errorMessage || 'OCR 模型状态检查失败')
    }
    applyOcrModelStatusPayload(payload)
    statusMessage.value = `${message} · ${ocrModelSummary.value}`
    return payload
  } catch (error) {
    ocrModelStatusLoaded.value = false
    statusMessage.value = `检查 OCR 模型失败: ${error instanceof Error ? error.message : String(error)}`
    return null
  } finally {
    ocrModelStatusLoading.value = false
  }
}

async function downloadOcrModel() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  ocrModelDownloadLoading.value = true

  try {
    const payload = await callDesktop('download_ocr_model')
    if (!payload?.success) {
      throw new Error(payload?.errorMessage || 'OCR 模型下载失败')
    }
    applyOcrModelStatusPayload(payload)
    statusMessage.value = payload?.downloaded
      ? 'OCR 模型已下载并完成校验'
      : `OCR 模型已就绪 · ${ocrModelSummary.value}`
  } catch (error) {
    statusMessage.value = `下载 OCR 模型失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    ocrModelDownloadLoading.value = false
  }
}

async function chooseGlobalDownloadDirectory() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  try {
    const payload = await callDesktop(
      'select_download_directory',
      normalizeGlobalDownloadDir(globalSettings.downloadDir)
    )
    const selectedPath = normalizeGlobalDownloadDir(payload?.selectedPath)
    if (!selectedPath) {
      statusMessage.value = '已取消选择下载目录'
      return
    }
    globalSettings.downloadDir = selectedPath
    statusMessage.value = `已选择下载目录：${selectedPath}`
  } catch (error) {
    statusMessage.value = `选择下载目录失败: ${error instanceof Error ? error.message : String(error)}`
  }
}

function clearGlobalDownloadDirectory() {
  globalSettings.downloadDir = ''
  statusMessage.value = '已清空下载目录，点击保存后会写入数据库'
}

async function loadModelSettings(message = '模型设置已载入') {
  if (!desktopReady.value) {
    return null
  }

  modelSettingsLoading.value = true

  try {
    const payload = await callDesktop('get_model_settings')
    applyModelSettingsPayload(payload)
    statusMessage.value = `${message} · 当前有 ${rewritePromptCount.value} 条改写提示词`
    return payload
  } catch (error) {
    modelSettingsLoaded.value = false
    statusMessage.value = `加载模型设置失败: ${error instanceof Error ? error.message : String(error)}`
    return null
  } finally {
    modelSettingsLoading.value = false
  }
}

function addRewritePrompt() {
  rewritePrompts.value = [...rewritePrompts.value, createRewritePromptItem('')]
  statusMessage.value = `已新增第 ${rewritePrompts.value.length} 条改写提示词`
}

function removeRewritePrompt(promptId) {
  rewritePrompts.value = rewritePrompts.value.filter((item) => item.id !== promptId)
  statusMessage.value = `已移除一条改写提示词，剩余 ${rewritePromptCount.value} 条`
}

async function saveModelSettings() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  modelSettingsSaving.value = true

  try {
    const payload = await callDesktop(
      'save_model_settings',
      modelSettings.baseUrl,
      modelSettings.apiKey,
      modelSettings.model,
      modelSettings.titlePrompt,
      rewritePrompts.value.map((item) => item.content)
    )
    applyModelSettingsPayload(payload)
    statusMessage.value = `模型设置已保存到数据库 · 改写提示词 ${rewritePromptCount.value} 条`
  } catch (error) {
    statusMessage.value = `保存模型设置失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    modelSettingsSaving.value = false
  }
}

async function testSavedModelConnection() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  const validationMessage = getModelParameterValidationMessage(
    modelSettings.baseUrl,
    modelSettings.apiKey,
    modelSettings.model
  )
  if (validationMessage) {
    statusMessage.value = validationMessage
    return
  }

  modelConnectionLoading.value = true
  try {
    const payload = await callDesktop(
      'test_model_connection',
      modelSettings.baseUrl,
      modelSettings.apiKey,
      modelSettings.model
    )
    statusMessage.value =
      payload?.success === false
        ? getModelActionMessage(payload, '模型连接测试失败')
        : getModelConnectionSuccessMessage(payload)
  } catch (error) {
    statusMessage.value = `模型连接测试失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    modelConnectionLoading.value = false
  }
}

async function testRewriteModelConnection() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  const validationMessage = getModelParameterValidationMessage(
    rewriteForm.baseUrl,
    rewriteForm.apiKey,
    rewriteForm.model
  )
  if (validationMessage) {
    rewriteErrorMessage.value = validationMessage
    statusMessage.value = validationMessage
    return
  }

  rewriteConnectionLoading.value = true
  try {
    const payload = await callDesktop(
      'test_model_connection',
      rewriteForm.baseUrl,
      rewriteForm.apiKey,
      rewriteForm.model
    )
    if (payload?.success === false) {
      rewriteErrorMessage.value = getModelActionMessage(payload, '模型连接测试失败')
      statusMessage.value = rewriteErrorMessage.value
      return
    }

    rewriteErrorMessage.value = ''
    statusMessage.value = getModelConnectionSuccessMessage(payload)
  } catch (error) {
    rewriteErrorMessage.value = `模型连接测试失败: ${error instanceof Error ? error.message : String(error)}`
    statusMessage.value = rewriteErrorMessage.value
  } finally {
    rewriteConnectionLoading.value = false
  }
}

async function rewriteArticleWithModel() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }
  const validationMessage = getModelParameterValidationMessage(
    rewriteForm.baseUrl,
    rewriteForm.apiKey,
    rewriteForm.model
  )
  if (validationMessage) {
    rewriteErrorMessage.value = validationMessage
    statusMessage.value = validationMessage
    return
  }
  if (Number(rewriteForm.promptId) <= 0) {
    rewriteErrorMessage.value = '请先选择一个已保存的改写提示词'
    statusMessage.value = '请先选择一个已保存的改写提示词'
    return
  }
  if (!rewriteForm.article.trim()) {
    rewriteErrorMessage.value = '请输入要改写的文章内容'
    statusMessage.value = '请输入要改写的文章内容'
    return
  }

  rewriteLoading.value = true
  try {
    const payload = await callDesktop(
      'rewrite_article',
      rewriteForm.baseUrl,
      rewriteForm.apiKey,
      rewriteForm.model,
      Number(rewriteForm.promptId),
      rewriteForm.article
    )
    if (payload?.success === false) {
      rewriteResult.value = null
      rewriteErrorMessage.value = getModelActionMessage(payload, '文章改写失败')
      statusMessage.value = rewriteErrorMessage.value
      return
    }
    rewriteResult.value = payload
    rewriteErrorMessage.value = ''
    statusMessage.value = `文章改写完成，输出 ${String(payload?.content || '').length} 个字符`
  } catch (error) {
    rewriteResult.value = null
    rewriteErrorMessage.value = `文章改写失败: ${error instanceof Error ? error.message : String(error)}`
    statusMessage.value = rewriteErrorMessage.value
  } finally {
    rewriteLoading.value = false
  }
}

async function testTitleModelConnection() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  const validationMessage = getModelParameterValidationMessage(
    titleForm.baseUrl,
    titleForm.apiKey,
    titleForm.model
  )
  if (validationMessage) {
    titleErrorMessage.value = validationMessage
    statusMessage.value = validationMessage
    return
  }

  titleConnectionLoading.value = true
  try {
    const payload = await callDesktop(
      'test_model_connection',
      titleForm.baseUrl,
      titleForm.apiKey,
      titleForm.model
    )
    if (payload?.success === false) {
      titleErrorMessage.value = getModelActionMessage(payload, '模型连接测试失败')
      statusMessage.value = titleErrorMessage.value
      return
    }

    titleErrorMessage.value = ''
    statusMessage.value = getModelConnectionSuccessMessage(payload)
  } catch (error) {
    titleErrorMessage.value = `模型连接测试失败: ${error instanceof Error ? error.message : String(error)}`
    statusMessage.value = titleErrorMessage.value
  } finally {
    titleConnectionLoading.value = false
  }
}

async function generateTitleWithModel() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }
  const validationMessage = getModelParameterValidationMessage(
    titleForm.baseUrl,
    titleForm.apiKey,
    titleForm.model
  )
  if (validationMessage) {
    titleErrorMessage.value = validationMessage
    statusMessage.value = validationMessage
    return
  }
  if (!titleForm.titlePrompt.trim()) {
    titleErrorMessage.value = '请输入标题提示词'
    statusMessage.value = '请输入标题提示词'
    return
  }
  if (!titleForm.article.trim()) {
    titleErrorMessage.value = '请输入要生成标题的文章内容'
    statusMessage.value = '请输入要生成标题的文章内容'
    return
  }

  titleLoading.value = true
  try {
    const payload = await callDesktop(
      'generate_title',
      titleForm.baseUrl,
      titleForm.apiKey,
      titleForm.model,
      titleForm.titlePrompt,
      titleForm.article
    )
    if (payload?.success === false) {
      titleResult.value = null
      titleErrorMessage.value = getModelActionMessage(payload, '标题生成失败')
      statusMessage.value = titleErrorMessage.value
      return
    }
    titleResult.value = payload
    titleErrorMessage.value = ''
    statusMessage.value = `标题生成完成，结果长度 ${String(payload?.title || '').length} 个字符`
  } catch (error) {
    titleResult.value = null
    titleErrorMessage.value = `标题生成失败: ${error instanceof Error ? error.message : String(error)}`
    statusMessage.value = titleErrorMessage.value
  } finally {
    titleLoading.value = false
  }
}

async function chooseImageForOcr() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  try {
    const payload = await callDesktop('select_image_file', imageOcrForm.imagePath)
    const selectedPath = String(payload?.selectedPath || '').trim()
    if (!selectedPath) {
      statusMessage.value = '已取消选择图片'
      return
    }
    imageOcrForm.imagePath = selectedPath
    imageOcrResult.value = null
    imageOcrErrorMessage.value = ''
    statusMessage.value = `已选择图片：${selectedPath}`
  } catch (error) {
    imageOcrErrorMessage.value = `选择图片失败: ${error instanceof Error ? error.message : String(error)}`
    statusMessage.value = imageOcrErrorMessage.value
  }
}

async function runImageOcr() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }
  if (!String(imageOcrForm.imagePath || '').trim()) {
    imageOcrErrorMessage.value = '请先选择一张图片'
    statusMessage.value = imageOcrErrorMessage.value
    return
  }

  imageOcrLoading.value = true
  try {
    const payload = await callDesktop('ocr_image_text', imageOcrForm.imagePath)
    if (payload?.success === false) {
      imageOcrResult.value = null
      imageOcrErrorMessage.value = getModelActionMessage(payload, '图片 OCR 识别失败')
      statusMessage.value = imageOcrErrorMessage.value
      return
    }
    imageOcrResult.value = payload
    imageOcrErrorMessage.value = ''
    statusMessage.value = `图片 OCR 完成，共识别 ${Number(payload?.lineCount || 0)} 行文本`
  } catch (error) {
    imageOcrResult.value = null
    imageOcrErrorMessage.value = `图片 OCR 识别失败: ${error instanceof Error ? error.message : String(error)}`
    statusMessage.value = imageOcrErrorMessage.value
  } finally {
    imageOcrLoading.value = false
  }
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function isProjectFinished(payload) {
  const project = payload?.project
  const progress = Number(project?.progress ?? 0)
  if (Number.isFinite(progress) && progress >= 100) {
    return true
  }

  const stateMessage = String(project?.state_message || '')
  return stateMessage.includes('项目处理完成')
}

function isProjectFailed(payload) {
  const stateMessage = String(payload?.project?.state_message || '')
  return /失败|异常|取消/.test(stateMessage)
}

function isProjectExportFinished(payload) {
  const progress = Number(payload?.progress ?? 0)
  const url = String(payload?.url || '').trim()
  return Number.isFinite(progress) && progress >= 100 && Boolean(url)
}

async function fetchProjectInfo(pid, accountCookies, message = '项目进度已刷新') {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return null
  }

  const normalizedPid = String(pid || '').trim()
  if (!normalizedPid) {
    statusMessage.value = '当前没有可轮询的 pid'
    return null
  }

  try {
    const payload = await callDesktop('get_project_info', accountCookies, normalizedPid)
    projectInfo.value = payload
    projectLastFetchAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
    await updateCurrentTaskStatus(projectStateText.value, normalizedPid, {
      progress: projectProgressValue.value,
      huashengStatus: projectStateText.value
    })
    statusMessage.value = `${message} · ${projectProgressValue.value}% · ${projectStateText.value}`
    return payload
  } catch (error) {
    statusMessage.value = `获取项目进度失败: ${error instanceof Error ? error.message : String(error)}`
    throw error
  }
}

async function pollProjectUntilFinished(pid, accountCookies) {
  stopProjectPolling()
  const currentToken = projectPollingToken
  projectPolling.value = true
  projectPollCount.value = 0

  try {
    for (let attempt = 1; attempt <= PROJECT_MAX_POLLS; attempt += 1) {
      if (currentToken !== projectPollingToken) {
        return
      }
      projectPollCount.value = attempt
      const payload = await fetchProjectInfo(
        pid,
        accountCookies,
        `第 ${attempt}/${PROJECT_MAX_POLLS} 次轮询`
      )
      if (currentToken !== projectPollingToken) {
        return
      }

      if (isProjectFailed(payload)) {
        statusMessage.value = `任务处理失败: ${projectStateText.value}`
        return { status: 'failed', payload }
      }

      if (isProjectFinished(payload)) {
        statusMessage.value = projectCanView.value
          ? `任务处理完成，可直接查看成片`
          : `任务处理完成`
        return { status: 'success', payload }
      }

      if (attempt < PROJECT_MAX_POLLS) {
        await sleep(PROJECT_POLL_INTERVAL_MS)
      }
    }

    statusMessage.value = `轮询结束，当前进度 ${projectProgressValue.value}%`
    return { status: 'timeout', payload: projectInfo.value }
  } finally {
    if (currentToken === projectPollingToken) {
      projectPolling.value = false
    }
  }
}

async function createProjectExport(projectId, accountCookies) {
  const normalizedProjectId = Number(projectId) || 0
  if (normalizedProjectId <= 0) {
    statusMessage.value = '项目已完成，但没有拿到可导出的项目 id'
    return null
  }

  projectExportLoading.value = true
  projectExportPollCount.value = 0
  projectExportInfo.value = null
  statusMessage.value = '字幕已设置，开始发起导出任务'

  try {
    const payload = await callDesktop('export_project_video', accountCookies, normalizedProjectId)
    projectExportTask.value = payload
    statusMessage.value = `导出任务已创建，开始轮询导出进度`
    return payload
  } catch (error) {
    statusMessage.value = `发起导出失败: ${error instanceof Error ? error.message : String(error)}`
    throw error
  } finally {
    projectExportLoading.value = false
  }
}

async function fetchProjectExportInfo(
  projectId,
  taskId,
  accountCookies,
  message = '导出进度已刷新'
) {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return null
  }

  const normalizedProjectId = Number(projectId) || 0
  const normalizedTaskId = String(taskId || '').trim()
  if (normalizedProjectId <= 0 || !normalizedTaskId) {
    statusMessage.value = '当前没有可轮询的导出任务'
    return null
  }

  try {
    const payload = await callDesktop(
      'get_project_export_info',
      accountCookies,
      normalizedProjectId,
      normalizedTaskId
    )
    projectExportInfo.value = payload
    projectLastFetchAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
    await updateCurrentTaskStatus(projectExportStateText.value, projectDisplayPid.value, {
      progress: projectExportProgressValue.value,
      videoUrl: projectExportInfo.value?.url || '',
      huashengStatus: projectExportStateText.value
    })
    statusMessage.value = `${message} · ${projectExportProgressValue.value}% · ${projectExportStateText.value}`
    return payload
  } catch (error) {
    statusMessage.value = `获取导出进度失败: ${error instanceof Error ? error.message : String(error)}`
    throw error
  }
}

async function pollProjectExportUntilFinished(projectId, taskId, accountCookies) {
  stopProjectPolling()
  const currentToken = projectPollingToken
  projectExportPolling.value = true
  projectExportPollCount.value = 0

  try {
    for (let attempt = 1; attempt <= PROJECT_EXPORT_MAX_POLLS; attempt += 1) {
      if (currentToken !== projectPollingToken) {
        return { status: 'cancelled', payload: projectExportInfo.value }
      }

      projectExportPollCount.value = attempt
      const payload = await fetchProjectExportInfo(
        projectId,
        taskId,
        accountCookies,
        `导出轮询 ${attempt}/${PROJECT_EXPORT_MAX_POLLS}`
      )

      if (currentToken !== projectPollingToken) {
        return { status: 'cancelled', payload }
      }

      if (isProjectExportFinished(payload)) {
        statusMessage.value = '导出完成，可直接查看成片'
        return { status: 'success', payload }
      }

      if (attempt < PROJECT_EXPORT_MAX_POLLS) {
        await sleep(PROJECT_EXPORT_POLL_INTERVAL_MS)
      }
    }

    statusMessage.value = `导出轮询结束，当前进度 ${projectExportProgressValue.value}%`
    return { status: 'timeout', payload: projectExportInfo.value }
  } finally {
    if (currentToken === projectPollingToken) {
      projectExportPolling.value = false
    }
  }
}

async function refreshProjectProgress() {
  const cookies = selectedProjectAccount.value?.cookies?.trim()
  if (!cookies) {
    statusMessage.value = '当前没有可刷新的任务进度'
    return
  }

  if (projectExportTask.value?.task_id && Number(projectDisplayId.value) > 0) {
    await fetchProjectExportInfo(
      projectDisplayId.value,
      projectExportTask.value.task_id,
      selectedProjectAccount.value.cookies,
      '已手动刷新导出进度'
    )
    return
  }

  const pid = projectDisplayPid.value
  if (pid === '--') {
    statusMessage.value = '当前没有可刷新的任务进度'
    return
  }

  await fetchProjectInfo(pid, selectedProjectAccount.value.cookies, '已手动刷新项目进度')
}

function openProjectView() {
  if (!projectViewUrl.value) {
    statusMessage.value = '当前还没有可查看的成片地址'
    return
  }

  window.open(projectViewUrl.value, '_blank', 'noopener,noreferrer')
}

async function copyProjectViewUrl() {
  if (!projectViewUrl.value) {
    statusMessage.value = '当前还没有可复制的成片地址'
    return
  }

  try {
    await copyText(projectViewUrl.value)
    statusMessage.value = '已复制成片地址'
  } catch (error) {
    statusMessage.value = `复制失败: ${error instanceof Error ? error.message : String(error)}`
  }
}

function applyPayload(payload) {
  accounts.value = payload.items ?? []
  stats.value = payload.stats ?? {
    total: 0,
    active: 0,
    disabled: 0
  }
  if (payload?.databasePath) {
    databasePath.value = payload.databasePath
  }
  lastSyncedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
}

function applyTaskPayload(payload) {
  taskRecords.value = [...(payload.items ?? [])].sort(
    (left, right) => Number(right?.id || 0) - Number(left?.id || 0)
  )
  if (payload?.databasePath) {
    databasePath.value = payload.databasePath
  }
}

async function loadTasks(message = '任务列表已同步', { silent = false } = {}) {
  if (!desktopReady.value) {
    return null
  }

  tasksLoading.value = true

  try {
    const payload = await callDesktop('list_tasks')
    applyTaskPayload(payload)
    if (!silent) {
      statusMessage.value = message
    }
    return payload
  } catch (error) {
    if (!silent) {
      statusMessage.value = `加载任务列表失败: ${error instanceof Error ? error.message : String(error)}`
    }
    return null
  } finally {
    tasksLoading.value = false
  }
}

async function deleteAllTaskRecords() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  if (!taskCount.value) {
    statusMessage.value = '当前没有可删除的任务'
    taskDeleteDialogOpen.value = false
    return
  }

  taskDeleteLoading.value = true

  try {
    const payload = await callDesktop('delete_all_task_records')
    taskDeleteDialogOpen.value = false
    taskStatusDialogOpen.value = false
    await loadTasks('任务列表已同步', { silent: true })
    statusMessage.value = `已删除 ${Number(payload?.deletedCount || 0)} 条任务`
  } catch (error) {
    statusMessage.value = `删除任务失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    taskDeleteLoading.value = false
  }
}

async function downloadTaskVideo(task) {
  const taskId = Number(task?.id) || 0
  if (taskId <= 0) {
    statusMessage.value = '任务数据无效，无法下载视频'
    return
  }
  if (!String(task?.videoUrl || '').trim()) {
    statusMessage.value = '当前任务还没有可下载的视频地址'
    return
  }
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }
  if (isTaskDownloading(taskId)) {
    return
  }

  setTaskDownloading(taskId, true)

  try {
    const payload = await callDesktop('download_task_video', taskId)
    await loadTasks('任务列表已同步', { silent: true })
    statusMessage.value = `视频已下载到 ${payload?.downloadPath || '--'}，任务已自动删除`
  } catch (error) {
    statusMessage.value = `下载视频失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    setTaskDownloading(taskId, false)
  }
}

async function retryTaskRecord(task) {
  const taskId = Number(task?.id) || 0
  if (taskId <= 0) {
    statusMessage.value = '任务数据无效，无法重试'
    return
  }
  if (!isTaskRetryable(task)) {
    statusMessage.value = '当前任务不是失败状态，无法重试'
    return
  }
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }
  if (isTaskRetrying(taskId)) {
    return
  }

  setTaskRetrying(taskId, true)

  try {
    const payload = await callDesktop('retry_task_record', taskId)
    await loadTasks('任务列表已同步', { silent: true })
    statusMessage.value = `任务 #${taskId} 已重试，当前状态 ${payload?.status || '--'}`
  } catch (error) {
    statusMessage.value = `重试任务失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    setTaskRetrying(taskId, false)
  }
}

async function createTaskRecordForCurrentProject(projectPayload) {
  const accountId = Number(selectedProjectAccount.value?.id) || 0
  const projectPid = String(projectPayload?.pid || '').trim()
  if (accountId <= 0 || !projectPid) {
    return null
  }

  const task = await callDesktop(
    'create_task_record',
    accountId,
    projectPid,
    '处理中',
    '任务已创建'
  )
  currentProjectTaskRecordId.value = Number(task?.id) || null
  await loadTasks('任务列表已同步', { silent: true })
  return task
}

async function updateCurrentTaskStatus(status, projectPid = undefined, options = {}) {
  const taskId = Number(currentProjectTaskRecordId.value) || 0
  if (taskId <= 0) {
    return null
  }

  const task = await callDesktop(
    'update_task_status',
    taskId,
    String(status || ''),
    projectPid,
    options?.progress,
    options?.videoUrl,
    options?.rewrittenContent,
    options?.title,
    options?.huashengStatus
  )
  await loadTasks('任务列表已同步', { silent: true })
  return task
}

async function loadSubtitleSettings(message = '字幕设置已载入') {
  if (!desktopReady.value) {
    return null
  }

  subtitleSettingsLoading.value = true

  try {
    const payload = await callDesktop('get_subtitle_settings')
    applySubtitleSettingsPayload(payload)
    statusMessage.value = `${message} · ${subtitleSettingsSummary.value}`
    return payload
  } catch (error) {
    subtitleSettingsLoaded.value = false
    statusMessage.value = `加载字幕设置失败: ${error instanceof Error ? error.message : String(error)}`
    return null
  } finally {
    subtitleSettingsLoading.value = false
  }
}

async function saveSubtitleSettings() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  subtitleSettingsSaving.value = true

  try {
    const payload = await callDesktop(
      'save_subtitle_settings',
      Number(subtitleSettings.fontSize) || DEFAULT_SUBTITLE_SETTINGS.fontSize,
      subtitleSettings.styleId
    )
    applySubtitleSettingsPayload(payload)
    statusMessage.value = `字幕设置已保存到数据库 · ${subtitleSettingsSummary.value}`
  } catch (error) {
    statusMessage.value = `保存字幕设置失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    subtitleSettingsSaving.value = false
  }
}

async function loadHuashengVoiceSettings(message = '音色设置已载入') {
  if (!desktopReady.value) {
    return null
  }

  huashengVoiceSettingsLoading.value = true

  try {
    const payload = await callDesktop('get_huasheng_voice_settings')
    applyHuashengVoiceSettingsPayload(payload)
    statusMessage.value = `${message} · ${huashengVoiceSummary.value}`
    return payload
  } catch (error) {
    huashengVoiceSettingsLoaded.value = false
    statusMessage.value = `加载音色设置失败: ${error instanceof Error ? error.message : String(error)}`
    return null
  } finally {
    huashengVoiceSettingsLoading.value = false
  }
}

async function saveHuashengVoiceSettingsFromSelection() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return null
  }

  if (!selectedTtsVoice.value) {
    statusMessage.value = '请先选择一个音色'
    return null
  }

  huashengVoiceSettingsSaving.value = true

  try {
    const payload = await callDesktop(
      'save_huasheng_voice_settings',
      Number(selectedTtsVoice.value.id) || 0,
      selectedTtsVoice.value.name || '',
      getVoiceCode(selectedTtsVoice.value),
      getVoiceTags(selectedTtsVoice.value),
      getVoicePreviewUrl(selectedTtsVoice.value),
      selectedTtsVoice.value.cover || '',
      Number(ttsPlaybackRate.value) || 1,
      normalizeHuashengMaxConcurrentTasks(huashengVoiceSettings.maxConcurrentTasksPerAccount)
    )
    applyHuashengVoiceSettingsPayload(payload)
    closeVoicePicker()
    statusMessage.value = `音色设置已保存到数据库 · ${huashengVoiceSummary.value}`
    return payload
  } catch (error) {
    statusMessage.value = `保存音色设置失败: ${error instanceof Error ? error.message : String(error)}`
    return null
  } finally {
    huashengVoiceSettingsSaving.value = false
  }
}

async function saveHuashengVoiceSettings() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return null
  }

  huashengVoiceSettingsSaving.value = true

  try {
    const payload = await callDesktop(
      'save_huasheng_voice_settings',
      Number(huashengVoiceSettings.voiceId) || 0,
      huashengVoiceSettings.voiceName || '',
      huashengVoiceSettings.voiceCode || '',
      huashengVoiceSettings.voiceTags || '',
      huashengVoiceSettings.previewUrl || '',
      huashengVoiceSettings.cover || '',
      Number(huashengVoiceSettings.speechRate) || DEFAULT_HUASHENG_VOICE_SETTINGS.speechRate,
      normalizeHuashengMaxConcurrentTasks(huashengVoiceSettings.maxConcurrentTasksPerAccount)
    )
    applyHuashengVoiceSettingsPayload(payload)
    statusMessage.value = `花生设置已保存到数据库 · ${huashengVoiceSummary.value}`
    return payload
  } catch (error) {
    statusMessage.value = `保存花生设置失败: ${error instanceof Error ? error.message : String(error)}`
    return null
  } finally {
    huashengVoiceSettingsSaving.value = false
  }
}

async function ensureSubtitleSettingsReady() {
  if (!subtitleSettingsLoaded.value || !selectedSubtitleStyle.value) {
    const payload = await loadSubtitleSettings('已加载字幕设置')
    if (!payload?.settings) {
      throw new Error('未能加载字幕设置')
    }
  }

  return resolveSubtitleSettings(subtitleSettings)
}

async function applyProjectSubtitleSettings(projectId, accountCookies) {
  const normalizedProjectId = Number(projectId) || 0
  if (normalizedProjectId <= 0) {
    throw new Error('项目处理完成，但没有拿到可设置字幕的项目 id')
  }

  const settings = await ensureSubtitleSettingsReady()
  projectSubtitleLoading.value = true
  statusMessage.value = '项目处理完成，开始设置字幕样式'

  try {
    const payload = await callDesktop(
      'edit_project',
      accountCookies,
      normalizedProjectId,
      Number(settings.fontSize) || DEFAULT_SUBTITLE_SETTINGS.fontSize,
      settings.fontColor,
      settings.outlineColor,
      Number(settings.outlineThick) || DEFAULT_SUBTITLE_SETTINGS.outlineThick
    )
    projectSubtitleResult.value = payload
    statusMessage.value = `字幕样式已设置 · ${subtitleSettingsSummary.value}`
    return payload
  } catch (error) {
    statusMessage.value = `设置字幕失败: ${error instanceof Error ? error.message : String(error)}`
    throw error
  } finally {
    projectSubtitleLoading.value = false
  }
}

async function exportCurrentProject() {
  statusMessage.value = '开始校验导出参数'

  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  const accountCookies = selectedProjectAccount.value?.cookies?.trim()
  if (!accountCookies) {
    statusMessage.value = '请先选择发布账号'
    return
  }

  if (projectBusy.value) {
    statusMessage.value = '当前任务仍在处理中，请稍后再导出'
    return
  }

  const normalizedPid = String(projectDisplayPid.value || '').trim()
  const normalizedProjectId = Number(projectDisplayId.value) || 0
  if (!normalizedPid || normalizedPid === '--' || normalizedProjectId <= 0) {
    statusMessage.value = '当前没有可导出的项目，请先创建任务'
    return
  }

  projectExportTask.value = null
  projectExportInfo.value = null
  projectExportPollCount.value = 0

  try {
    const latestInfo = await fetchProjectInfo(
      normalizedPid,
      accountCookies,
      '导出前已刷新项目进度'
    )
    if (isProjectFailed(latestInfo)) {
      statusMessage.value = `任务处理失败，无法导出: ${projectStateText.value}`
      return
    }
    if (!isProjectFinished(latestInfo)) {
      statusMessage.value = `项目尚未处理完成，当前 ${projectProgressValue.value}%`
      return
    }

    await updateCurrentTaskStatus('设置字幕中', normalizedPid, {
      huashengStatus: projectStateText.value
    })
    await applyProjectSubtitleSettings(normalizedProjectId, accountCookies)
    await updateCurrentTaskStatus('导出中', normalizedPid, {
      huashengStatus: '准备导出'
    })
    const exportTask = await createProjectExport(normalizedProjectId, accountCookies)
    if (!exportTask?.task_id) {
      return
    }
    const exportResult = await pollProjectExportUntilFinished(
      normalizedProjectId,
      exportTask.task_id,
      accountCookies
    )
    if (exportResult?.status === 'success') {
      await updateCurrentTaskStatus('导出完成', normalizedPid, {
        huashengStatus: projectExportStateText.value
      })
      return
    }
    if (exportResult?.status === 'timeout') {
      await updateCurrentTaskStatus('导出超时', normalizedPid, {
        huashengStatus: projectExportStateText.value
      })
      return
    }
  } catch (error) {
    await updateCurrentTaskStatus('导出失败', normalizedPid, {
      huashengStatus: projectExportStateText.value || projectStateText.value || '导出失败'
    })
    statusMessage.value = `导出失败: ${error instanceof Error ? error.message : String(error)}`
  }
}

function formatDateTime(value) {
  if (!value) {
    return '--'
  }

  return value.replace('T', ' ')
}

function formatByteSize(value) {
  const size = Number(value || 0)
  if (!Number.isFinite(size) || size <= 0) {
    return '--'
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let currentSize = size
  let index = 0
  while (currentSize >= 1024 && index < units.length - 1) {
    currentSize /= 1024
    index += 1
  }
  return `${currentSize >= 100 || index === 0 ? currentSize.toFixed(0) : currentSize.toFixed(1)} ${units[index]}`
}

function getTaskTextPreview(value, limit = 64) {
  const text = String(value || '').trim()
  if (!text) {
    return '--'
  }
  const chars = Array.from(text)
  if (chars.length <= limit) {
    return text
  }
  return `${chars.slice(0, limit).join('')}……`
}

function getTaskPrimaryText(task) {
  const title = String(task?.title || '').trim()
  if (title) {
    return title
  }

  return String(task?.rewrittenContent || task?.articlePreview || '').trim()
}

function getTaskListPreview(task) {
  const text = getTaskPrimaryText(task)
  if (!text) {
    return '--'
  }
  return getTaskTextPreview(text, 10)
}

function isTaskHuashengProcessing(task) {
  const status = String(task?.status || '').trim()
  return status === 'S4扫描中' || status === 'S4导出中'
}

function isTaskWaitingForAvailableAccount(task) {
  const status = String(task?.status || '').trim()
  const huashengStatus = String(task?.huashengStatus || '').trim()
  return (
    status === '待创建花生任务' &&
    huashengStatus === '暂无可用花生账号，等待下次扫描'
  )
}

function getTaskDisplayStatus(task) {
  if (isTaskWaitingForAvailableAccount(task)) {
    return '等待可用账号'
  }
  return String(task?.status || '').trim() || '--'
}

function getTaskStatusDetail(task) {
  const status = String(task?.status || '').trim()
  const progress = Number(task?.progress || 0)
  const huashengStatus = String(task?.huashengStatus || '').trim()

  if (status === '待处理') {
    return '排队中'
  }

  if (status === '触发红线') {
    return huashengStatus || '禁止改写'
  }

  if (isTaskWaitingForAvailableAccount(task)) {
    return '下次扫描会自动重试'
  }

  if (isTaskHuashengProcessing(task)) {
    if (progress > 0) {
      return `当前进度 ${progress}%`
    }
    if (huashengStatus && huashengStatus !== status) {
      return huashengStatus
    }
    return '扫描中'
  }

  return ''
}

function buildTaskStatusSummaryItems(tasks, selector) {
  const counts = new Map()

  for (const task of tasks ?? []) {
    const label = String(selector(task) || '').trim() || '未设置'
    counts.set(label, Number(counts.get(label) || 0) + 1)
  }

  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'))
}

function getCookiesPreview(value) {
  if (!value) {
    return ''
  }

  if (value.length <= 140) {
    return value
  }

  return `${value.slice(0, 140)}...`
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', 'readonly')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

function maskPhone(value) {
  const normalized = String(value || '')
  if (normalized.length !== 11) {
    return normalized || '--'
  }

  return `${normalized.slice(0, 3)}****${normalized.slice(-4)}`
}

function pickRandomDebugAccount() {
  if (!debugAccountPool.value.length) {
    return null
  }

  const randomIndex = Math.floor(Math.random() * debugAccountPool.value.length)
  return debugAccountPool.value[randomIndex]
}

function getVoiceCode(voice) {
  return voice?.extra_json?.voice || ''
}

function getVoiceTags(voice) {
  return voice?.pool_extra_json?.tts_tags || '未标注风格'
}

function getVoicePreviewUrl(voice) {
  return voice?.pool_extra_json?.preview_url || ''
}

function normalizeTtsPlaybackRate(value, fallback = 1) {
  const normalized = Number(value)
  if (!Number.isFinite(normalized) || normalized < 0.5 || normalized > 2) {
    return fallback
  }

  return Number(normalized.toFixed(1))
}

function shouldSyncVoicePickerToProject() {
  return voicePickerTarget.value !== 'settings'
}

function syncProjectSpeechRate(value) {
  const normalized = normalizeTtsPlaybackRate(value, Number(projectForm.speechRate) || 1)
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return
  }

  if (Number(projectForm.speechRate) !== normalized) {
    projectForm.speechRate = normalized
  }
}

function selectTtsVoice(voice) {
  selectedTtsVoiceId.value = String(voice.id)
  if (shouldSyncVoicePickerToProject()) {
    syncProjectSpeechRate(ttsPlaybackRate.value)
  }
  statusMessage.value = `已选择音色 ${voice.name}`
}

async function copyVoiceCode(voice) {
  const voiceCode = getVoiceCode(voice)
  if (!voiceCode) {
    statusMessage.value = `${voice.name} 没有可复制的 voice code`
    return
  }

  try {
    await copyText(voiceCode)
    statusMessage.value = `已复制 ${voice.name} 的 voice code`
  } catch (error) {
    statusMessage.value = `复制失败: ${error instanceof Error ? error.message : String(error)}`
  }
}

function stopVoicePreview() {
  if (!previewAudio) {
    return
  }

  previewAudio.pause()
  previewAudio.currentTime = 0
  ttsPreviewing.value = false
}

async function previewSelectedVoice() {
  if (ttsPreviewing.value) {
    stopVoicePreview()
    statusMessage.value = '已停止试听'
    return
  }

  if (!selectedTtsVoice.value) {
    statusMessage.value = '请先选择一个音色'
    return
  }

  const previewUrl = getVoicePreviewUrl(selectedTtsVoice.value)
  if (!previewUrl) {
    statusMessage.value = `${selectedTtsVoice.value.name} 没有试听链接`
    return
  }

  stopVoicePreview()
  previewAudio = new Audio(previewUrl)
  previewAudio.playbackRate = ttsPlaybackRate.value
  previewAudio.onended = () => {
    ttsPreviewing.value = false
  }
  previewAudio.onerror = () => {
    ttsPreviewing.value = false
    statusMessage.value = `试听失败: ${selectedTtsVoice.value?.name || '当前音色'}`
  }

  try {
    await previewAudio.play()
    ttsPreviewing.value = true
    statusMessage.value = `正在试听 ${selectedTtsVoice.value.name}`
  } catch (error) {
    ttsPreviewing.value = false
    statusMessage.value = `试听失败: ${error instanceof Error ? error.message : String(error)}`
  }
}

function useSelectedVoiceForProject() {
  if (!selectedTtsVoice.value) {
    statusMessage.value = '请先在音色选择里选中一个音色'
    return
  }

  projectForm.voiceId = Number(selectedTtsVoice.value.id)
  syncProjectSpeechRate(ttsPlaybackRate.value)
  if (voicePickerDialogOpen.value) {
    closeVoicePicker()
    statusMessage.value = `已选择音色 ${selectedTtsVoice.value.name}，语速 ${projectForm.speechRate}`
    return
  }
  setActiveDebugTab('project')
  statusMessage.value = `已带入音色 ${selectedTtsVoice.value.name} 到创建任务，语速 ${projectForm.speechRate}`
}

async function openProjectVoicePicker() {
  stopVoicePreview()
  voicePickerTarget.value = 'project'
  if (Number(projectForm.voiceId) > 0) {
    selectedTtsVoiceId.value = String(projectForm.voiceId)
  }
  ttsPlaybackRate.value = normalizeTtsPlaybackRate(
    projectForm.speechRate,
    Number(ttsPlaybackRate.value) || 1
  )
  voicePickerDialogOpen.value = true
  statusMessage.value = '请选择一个音色并带入创建任务'
  await fetchTtsVoices('音色选择弹窗已载入', {
    preferredVoiceId: String(projectForm.voiceId || selectedTtsVoiceId.value || '')
  })
}

async function openSettingsVoicePicker() {
  stopVoicePreview()
  voicePickerTarget.value = 'settings'
  if (Number(huashengVoiceSettings.voiceId) > 0) {
    selectedTtsVoiceId.value = String(huashengVoiceSettings.voiceId)
  }
  ttsPlaybackRate.value = normalizeTtsPlaybackRate(
    huashengVoiceSettings.speechRate,
    DEFAULT_HUASHENG_VOICE_SETTINGS.speechRate
  )
  voicePickerDialogOpen.value = true
  statusMessage.value = '请选择默认音色并保存到数据库'
  await fetchTtsVoices('音色选择弹窗已载入', {
    preferredVoiceId: String(huashengVoiceSettings.voiceId || selectedTtsVoiceId.value || '')
  })
}

function editAccount(account) {
  setActiveSection('accounts')
  form.id = account.id
  form.phone = account.phone
  form.cookies = account.cookies
  form.note = account.note
  form.isDisabled = account.isDisabled
  accountDialogOpen.value = true
  statusMessage.value = `正在编辑 ${account.phone}`
}

async function loadAccounts(message = '账号列表已同步') {
  if (!desktopReady.value) {
    return
  }

  loading.value = true

  try {
    const payload = await callDesktop('list_accounts')
    applyPayload(payload)
    statusMessage.value = message
  } catch (error) {
    statusMessage.value = `加载失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

async function submitForm() {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  saving.value = true

  try {
    const editing = isEditing.value
    const payload = editing
      ? await callDesktop(
          'update_account',
          form.id,
          form.phone,
          form.cookies,
          form.note,
          form.isDisabled
        )
      : await callDesktop(
          'create_account',
          form.phone,
          form.cookies,
          form.note,
          form.isDisabled
        )

    applyPayload(payload)
    statusMessage.value = editing ? '账号已更新' : '账号已添加'
    closeAccountDialog()
  } catch (error) {
    statusMessage.value = `提交失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    saving.value = false
  }
}

async function toggleAccountDisabled(account) {
  busyAccountId.value = account.id

  try {
    const payload = await callDesktop(
      'set_account_disabled',
      account.id,
      !account.isDisabled
    )
    applyPayload(payload)
    statusMessage.value = account.isDisabled
      ? `已启用 ${account.phone}`
      : `已禁用 ${account.phone}`
  } catch (error) {
    statusMessage.value = `状态切换失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    busyAccountId.value = null
  }
}

async function copyCookies(account) {
  try {
    await copyText(account.cookies)
    statusMessage.value = `已复制 ${account.phone} 的 Cookies`
  } catch (error) {
    statusMessage.value = `复制失败: ${error instanceof Error ? error.message : String(error)}`
  }
}

async function fetchTtsVoices(message = '音色列表已载入', options = {}) {
  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  const account = pickRandomDebugAccount()
  if (!account?.cookies?.trim()) {
    statusMessage.value = '没有可用于调试的账号，请先添加账号并填写 Cookies'
    return
  }

  ttsLoading.value = true

  try {
    const preferredVoiceId = String(options?.preferredVoiceId || '').trim()
    const previousVoiceId = String(selectedTtsVoiceId.value || '').trim()
    const payload = await callDesktop(
      'list_tts_voices',
      account.cookies,
      Number(ttsRequest.pn) || 1,
      Number(ttsRequest.ps) || 50,
      Number(ttsRequest.categoryId) || 0
    )
    const materials = payload.materials ?? []

    ttsMaterials.value = materials
    ttsCategories.value = payload.categories ?? []
    ttsPage.value = payload.page ?? null
    ttsLastUsedVoiceId.value = String(payload.last_used_voice_id ?? '')
    if (
      preferredVoiceId &&
      materials.some((voice) => String(voice.id) === preferredVoiceId)
    ) {
      selectedTtsVoiceId.value = preferredVoiceId
    } else if (
      previousVoiceId &&
      materials.some((voice) => String(voice.id) === previousVoiceId)
    ) {
      selectedTtsVoiceId.value = previousVoiceId
    } else {
      selectedTtsVoiceId.value = String(payload.last_used_voice_id ?? materials[0]?.id ?? '')
    }
    ttsLastFetchAccount.value = account
    ttsLastFetchAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
    statusMessage.value = `${message}，随机使用账号 ${maskPhone(account.phone)}，返回 ${materials.length} 个音色`
  } catch (error) {
    ttsMaterials.value = []
    ttsCategories.value = []
    ttsPage.value = null
    ttsLastUsedVoiceId.value = ''
    selectedTtsVoiceId.value = ''
    ttsLastFetchAccount.value = account
    statusMessage.value = `获取音色失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    ttsLoading.value = false
  }
}

function changeTtsCategory(categoryId) {
  ttsRequest.categoryId = Number(categoryId)
  if (debugAccountPool.value.length) {
    fetchTtsVoices(`已切换到 ${ttsCategoryOptions.value.find((item) => item.id === Number(categoryId))?.title || '当前'} 分类`)
  }
}

async function createProjectTask() {
  statusMessage.value = '开始校验创建任务参数'

  if (!desktopReady.value) {
    statusMessage.value = '当前不在 PyWebView 环境内'
    return
  }

  if (!selectedProjectAccount.value?.cookies?.trim()) {
    statusMessage.value = '请先选择发布账号'
    return
  }

  const voiceId = Number(projectForm.voiceId) || 0
  if (voiceId <= 0) {
    statusMessage.value = '请先点击选择音色'
    return
  }

  stopProjectPolling()
  currentProjectTaskRecordId.value = null
  projectInfo.value = null
  projectPollCount.value = 0
  projectSubtitleResult.value = null
  projectExportTask.value = null
  projectExportInfo.value = null
  projectExportPollCount.value = 0
  projectLoading.value = true
  statusMessage.value = '开始调用创建任务接口'
  let createdPayload = null

  try {
    const accountCookies = selectedProjectAccount.value.cookies
    const payload = await callDesktop(
      'create_project',
      accountCookies,
      projectForm.name,
      projectForm.script,
      voiceId,
      0,
      0,
      '',
      Number(projectForm.speechRate) || 1,
      1,
      0,
      1,
      0,
      0
    )
    createdPayload = payload
    projectResult.value = payload
    projectLastFetchAccount.value = selectedProjectAccount.value
    projectLastFetchAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
    await createTaskRecordForCurrentProject(payload)
    statusMessage.value = `创建任务成功，开始轮询任务进度`
    projectLoading.value = false
    const pollResult = await pollProjectUntilFinished(payload?.pid, accountCookies)
    if (pollResult?.status === 'failed') {
      await updateCurrentTaskStatus('处理失败', payload?.pid, {
        huashengStatus: projectStateText.value
      })
      return
    }
    if (pollResult?.status === 'timeout') {
      await updateCurrentTaskStatus('处理超时', payload?.pid, {
        huashengStatus: projectStateText.value
      })
      return
    }
    if (pollResult?.status !== 'success') {
      return
    }

    await updateCurrentTaskStatus('任务处理完成', payload?.pid, {
      huashengStatus: projectStateText.value
    })
    statusMessage.value = '任务处理完成，可点击导出按钮'
  } catch (error) {
    if (!createdPayload) {
      projectResult.value = null
    } else {
      await updateCurrentTaskStatus('任务异常', createdPayload?.pid, {
        huashengStatus: projectStateText.value || '任务异常'
      })
    }
    projectLastFetchAccount.value = selectedProjectAccount.value
    statusMessage.value = createdPayload
      ? `任务已创建，但后续处理失败: ${error instanceof Error ? error.message : String(error)}`
      : `创建任务失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    projectLoading.value = false
  }
}

function handleDesktopEvent(event) {
  if (!event?.type) {
    return
  }

  if (event.type === 'accounts.refresh-requested') {
    loadAccounts('账号列表已从菜单刷新')
    return
  }

  if (event.type === 'accounts.created' && event.payload?.account?.phone) {
    statusMessage.value = `已添加 ${event.payload.account.phone}`
    return
  }

  if (event.type === 'accounts.updated' && event.payload?.account?.phone) {
    statusMessage.value = `已更新 ${event.payload.account.phone}`
    return
  }

  if (event.type === 'accounts.status-changed' && event.payload?.account?.phone) {
    statusMessage.value = `${event.payload.account.phone} 状态已变更`
  }
}

async function bindPyWebView() {
  desktopReady.value = hasDesktopApi()

  if (desktopReady.value) {
    await loadAppState()
    await loadAccounts('账号列表已载入')
    const tasksPayload = await loadTasks('任务列表已载入', { silent: true })
    const globalPayload = await loadGlobalSettings('全局设置已载入')
    const subtitlePayload = await loadSubtitleSettings('字幕设置已载入')
    const voicePayload = await loadHuashengVoiceSettings('音色设置已载入')
    const modelPayload = await loadModelSettings('模型设置已载入')
    if (tasksPayload && globalPayload && subtitlePayload && voicePayload && modelPayload) {
      statusMessage.value = '账号列表、任务列表和全部设置已载入'
    } else if (tasksPayload && globalPayload && subtitlePayload && voicePayload) {
      statusMessage.value = '账号列表、任务列表和花生设置已载入'
    } else if (tasksPayload && globalPayload && modelPayload) {
      statusMessage.value = '账号列表、任务列表和模型设置已载入'
    } else if (tasksPayload && subtitlePayload && voicePayload) {
      statusMessage.value = '账号列表、任务列表和花生设置已载入'
    } else if (tasksPayload && modelPayload) {
      statusMessage.value = '账号列表、任务列表和模型设置已载入'
    } else if (subtitlePayload && voicePayload) {
      statusMessage.value = '账号列表和花生设置已载入'
    } else if (modelPayload) {
      statusMessage.value = '账号列表和模型设置已载入'
    }
  } else {
    statusMessage.value = '当前为浏览器预览模式，数据库功能仅在 PyWebView 中可用'
  }
}

onMounted(() => {
  unsubscribeDesktopEvents = subscribeDesktopEvents(handleDesktopEvent)
  startTaskListAutoRefresh()
  bindPyWebView()
  window.addEventListener('pywebviewready', bindPyWebView, { once: true })
})

onUnmounted(() => {
  stopTaskListAutoRefresh()
  stopProjectPolling()
  stopVoicePreview()
  unsubscribeDesktopEvents?.()
})

watch(ttsPlaybackRate, (value) => {
  if (previewAudio) {
    previewAudio.playbackRate = value
  }
  if (shouldSyncVoicePickerToProject()) {
    syncProjectSpeechRate(value)
  }
})

watch(selectedTtsVoiceId, (value) => {
  if (value && shouldSyncVoicePickerToProject()) {
    projectForm.voiceId = Number(value)
  }
})
</script>

<template>
  <main class="admin-shell">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-badge" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 8.5 12 4l8 4.5-8 4.5-8-4.5Z" />
            <path d="M4 15.5 12 20l8-4.5" />
            <path d="M4 12 12 16.5 20 12" />
          </svg>
        </div>
        <div>
          <h1>花生 AI</h1>
          <p class="brand-subtitle">桌面账号控制台</p>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="Main navigation">
        <button
          v-for="item in navigationItems"
          :key="item.key"
          type="button"
          class="nav-item"
          :data-active="activeSection === item.key"
          @click="switchSection(item.key)"
        >
          <span class="nav-icon" v-html="item.icon"></span>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="sidebar-status">
          <span class="status-dot" :data-active="desktopReady"></span>
          <span>{{ desktopReady ? '桌面桥接已连接' : '浏览器预览模式' }}</span>
        </div>
        <p class="sidebar-note">
          参考微头条控制台的线性后台风格，保留本地桌面账号管理交互。
        </p>
        <p class="sidebar-version">HuaShengAI {{ displayAppVersion }}</p>
      </div>
    </aside>

    <section class="content-shell">
      <section
        v-if="visitedSections.accounts"
        v-show="activeSection === 'accounts'"
        class="page-body accounts-page"
      >
        <div class="list-toolbar">
          <label class="search-field">
            <input
              v-model="searchKeyword"
              type="text"
              placeholder="搜索手机号、备注或 Cookies"
            />
          </label>

          <div class="filter-group">
            <button
              type="button"
              class="filter-pill"
              :data-active="filterMode === 'all'"
              @click="filterMode = 'all'"
            >
              全部
            </button>
            <button
              type="button"
              class="filter-pill"
              :data-active="filterMode === 'enabled'"
              @click="filterMode = 'enabled'"
            >
              已启用
            </button>
            <button
              type="button"
              class="filter-pill"
              :data-active="filterMode === 'disabled'"
              @click="filterMode = 'disabled'"
            >
              已禁用
            </button>
          </div>

          <button
            type="button"
            class="toolbar-button primary"
            @click="openCreateAccountDialog"
          >
            添加账号
          </button>
        </div>

        <div class="account-list">
            <article
              v-for="account in filteredAccounts"
              :key="account.id"
              class="account-card"
              :data-disabled="account.isDisabled"
            >
              <div class="account-top">
                <div>
                  <p class="account-phone">{{ account.phone }}</p>
                  <p class="account-note">{{ account.note || '未填写备注' }}</p>
                  <p class="account-generation-count">
                    今日制作 {{ account.todayGenerationCount ?? 0 }}/{{ account.dailyGenerationLimit ?? 50 }}
                  </p>
                  <p class="account-generation-count">
                    活跃花生任务 {{ account.activeHuashengTaskCount ?? 0 }}/{{ account.maxConcurrentTasksPerAccount ?? 1 }}
                  </p>
                </div>
                <span class="status-chip" :data-disabled="account.isDisabled">
                  {{ account.isDisabled ? '已禁用' : '正常可用' }}
                </span>
              </div>

              <div class="account-meta">
                <span>创建于 {{ formatDateTime(account.createdAt) }}</span>
                <span>更新于 {{ formatDateTime(account.updatedAt) }}</span>
              </div>

              <div class="cookies-box">
                <span>Cookies</span>
                <pre>{{ getCookiesPreview(account.cookies) }}</pre>
              </div>

              <div class="account-actions">
                <button type="button" class="toolbar-button secondary" @click="editAccount(account)">
                  编辑
                </button>
                <button type="button" class="toolbar-button secondary" @click="copyCookies(account)">
                  复制 Cookies
                </button>
                <button
                  type="button"
                  class="toolbar-button primary"
                  :disabled="busyAccountId === account.id"
                  @click="toggleAccountDisabled(account)"
                >
                  {{
                    busyAccountId === account.id
                      ? '处理中...'
                      : account.isDisabled
                        ? '启用账号'
                        : '禁用账号'
                  }}
                </button>
              </div>
            </article>

            <div v-if="!filteredAccounts.length" class="empty-state">
              <p>没有匹配的账号</p>
              <span>可以先点击右上角添加账号，或者调整筛选条件。</span>
            </div>
          </div>
      </section>

      <section
        v-if="visitedSections.tasks"
        v-show="activeSection === 'tasks'"
        class="page-body tasks-page"
      >
        <div class="list-toolbar">
          <div class="tasks-toolbar-copy">
            <strong>任务列表</strong>
            <span>展示任务标题预览和当前状态，右上角可查看状态数量统计。</span>
          </div>

          <div class="panel-actions">
            <button
              type="button"
              class="toolbar-button secondary"
              @click="openTaskStatusDialog"
            >
              状态查看
            </button>
            <button
              type="button"
              class="toolbar-button danger"
              :disabled="tasksLoading || taskDeleteLoading || !desktopReady || !taskCount"
              @click="openTaskDeleteDialog"
            >
              {{ taskDeleteLoading ? '删除中...' : '全部删除' }}
            </button>
            <button
              type="button"
              class="toolbar-button secondary"
              :disabled="tasksLoading || !desktopReady"
              @click="loadTasks('任务列表已刷新')"
            >
              {{ tasksLoading ? '刷新中...' : '刷新列表' }}
            </button>
            <button
              type="button"
              class="toolbar-button primary"
              disabled
            >
              添加任务
            </button>
          </div>
        </div>

        <div v-if="taskCount" class="task-table-shell">
          <div class="task-table">
            <div class="task-table-head">
              <span>ID</span>
              <span>标题 / 文本</span>
              <span>状态</span>
              <span>重试</span>
              <span>下载</span>
            </div>

            <article
              v-for="task in taskRecords"
              :key="task.id"
              class="task-table-row"
            >
              <span class="task-cell task-cell-id">{{ task.id }}</span>
              <span
                class="task-cell task-cell-preview"
                :title="getTaskPrimaryText(task) || '--'"
              >
                {{ getTaskListPreview(task) }}
              </span>
              <span class="task-cell task-cell-status">
                <span class="task-status-content">
                  <span class="task-status-chip">{{ getTaskDisplayStatus(task) }}</span>
                  <small v-if="getTaskStatusDetail(task)" class="task-status-detail">
                    {{ getTaskStatusDetail(task) }}
                  </small>
                </span>
              </span>
              <span class="task-cell task-cell-actions">
                <button
                  v-if="isTaskRetryable(task)"
                  type="button"
                  class="toolbar-button secondary task-retry-button"
                  :disabled="isTaskRetrying(task.id) || !desktopReady"
                  @click="retryTaskRecord(task)"
                >
                  {{ isTaskRetrying(task.id) ? '重试中...' : '重试' }}
                </button>
                <span v-else class="task-download-placeholder">--</span>
              </span>
              <span class="task-cell task-cell-actions">
                <button
                  v-if="task.videoUrl"
                  type="button"
                  class="toolbar-button secondary task-download-button"
                  :disabled="isTaskDownloading(task.id) || !desktopReady"
                  @click="downloadTaskVideo(task)"
                >
                  {{ isTaskDownloading(task.id) ? '下载中...' : '下载' }}
                </button>
                <span v-else class="task-download-placeholder">--</span>
              </span>
            </article>
          </div>
        </div>

        <div v-else class="empty-state">
          <p>还没有任务记录</p>
          <span>可以先去文章列表执行全量处理，或者在调试界面创建任务。</span>
        </div>
      </section>

      <section
        v-if="visitedSections.benchmarkAccounts"
        v-show="activeSection === 'benchmarkAccounts'"
        class="page-body benchmark-accounts-page"
      >
        <BenchmarkAccountsSection
          :desktop-ready="desktopReady"
          @status="statusMessage = $event"
          @database-path="databasePath = $event"
        />
      </section>

      <section
        v-if="visitedSections.articleMonitoring"
        v-show="activeSection === 'articleMonitoring'"
        class="page-body article-monitoring-page"
      >
        <ArticleMonitoringSection
          :desktop-ready="desktopReady"
          @status="statusMessage = $event"
          @database-path="databasePath = $event"
        />
      </section>

      <section
        v-if="visitedSections.articleLibrary"
        v-show="activeSection === 'articleLibrary'"
        class="page-body article-library-page"
      >
        <ArticleLibrarySection
          :desktop-ready="desktopReady"
          @status="statusMessage = $event"
          @database-path="databasePath = $event"
          @tasks-created="loadTasks('任务列表已同步', { silent: true })"
        />
      </section>

      <section
        v-if="visitedSections.debug"
        v-show="activeSection === 'debug'"
        class="page-body debug-page"
      >
        <div class="debug-shell">
          <div class="debug-tabs" role="tablist" aria-label="Debug tabs">
            <button
              v-for="tab in debugTabs"
              :key="tab.key"
              type="button"
              class="debug-tab"
              :data-active="activeDebugTab === tab.key"
              @click="activateDebugTab(tab.key)"
            >
              <strong>{{ tab.label }}</strong>
              <small>{{ tab.description }}</small>
            </button>
          </div>

          <section
            v-if="visitedDebugTabs.tts"
            v-show="activeDebugTab === 'tts'"
            class="debug-panel"
          >
            <article class="tts-lab">
              <div class="tts-lab-header">
                <div>
                  <p class="tts-caption">花生调试台</p>
                  <h2>公共音色</h2>
                  <p class="tts-description">每次请求会随机抽取一个可用账号的 Cookies 去获取音色列表。</p>
                </div>
                <button
                  type="button"
                  class="toolbar-button secondary tts-refresh-button"
                  :disabled="ttsLoading"
                  @click="fetchTtsVoices('公共音色已刷新')"
                >
                  {{ ttsLoading ? '加载中...' : '随机账号刷新' }}
                </button>
              </div>

              <div class="tts-account-strip">
                <div class="tts-account-card">
                  <span>随机账号</span>
                  <strong>{{ ttsLastFetchAccount ? maskPhone(ttsLastFetchAccount.phone) : '尚未发起请求' }}</strong>
                  <small>
                    {{
                      ttsLastFetchAccount
                        ? ttsLastFetchAccount.note || '未填写备注'
                        : `可用账号池 ${debugAccountPool.length} 个`
                    }}
                  </small>
                </div>
                <div class="tts-account-card">
                  <span>接口状态</span>
                  <strong>{{ ttsLoading ? '加载音色中...' : '等待操作' }}</strong>
                  <small>{{ statusMessage }}</small>
                </div>
                <div class="tts-account-card">
                  <span>最近同步</span>
                  <strong>{{ ttsLastFetchAt || '--' }}</strong>
                  <small>总数 {{ ttsPage?.total || ttsMaterials.length }} · 上次使用 {{ ttsLastUsedVoiceId || '--' }}</small>
                </div>
              </div>

              <div class="tts-source-tabs" role="tablist" aria-label="Voice source tabs">
                <button
                  type="button"
                  class="tts-source-tab"
                  :data-active="ttsSourceTab === 'clone'"
                  :disabled="true"
                >
                  我的克隆音色
                </button>
                <button
                  type="button"
                  class="tts-source-tab"
                  :data-active="ttsSourceTab === 'public'"
                  @click="ttsSourceTab = 'public'"
                >
                  公共音色
                </button>
              </div>

              <div class="tts-category-tabs">
                <button
                  v-for="category in ttsCategoryOptions"
                  :key="category.id"
                  type="button"
                  class="tts-category-tab"
                  :data-active="ttsRequest.categoryId === category.id"
                  @click="changeTtsCategory(category.id)"
                >
                  {{ category.title }}
                </button>
              </div>

              <div v-if="ttsMaterials.length" class="tts-voice-grid">
                <button
                  v-for="voice in ttsMaterials"
                  :key="voice.id"
                  type="button"
                  class="tts-voice-card"
                  :data-active="String(selectedTtsVoiceId) === String(voice.id)"
                  @click="selectTtsVoice(voice)"
                >
                  <span
                    v-if="String(voice.id) === ttsLastUsedVoiceId"
                    class="tts-last-used-badge"
                  >
                    上次使用
                  </span>
                  <div class="tts-voice-cover-wrap">
                    <img
                      v-if="voice.cover"
                      class="tts-voice-cover"
                      :src="voice.cover"
                      :alt="voice.name"
                    />
                    <div v-else class="tts-voice-cover tts-voice-cover-placeholder">
                      {{ voice.name.slice(0, 1) }}
                    </div>
                  </div>
                  <div class="tts-voice-copy">
                    <strong>{{ voice.name }}</strong>
                    <span>{{ getVoiceTags(voice) }}</span>
                  </div>
                </button>
              </div>

              <div v-else class="tts-empty-state">
                {{ ttsLoading ? '正在加载公共音色...' : '还没有音色数据，点击右上角随机账号刷新。' }}
              </div>

              <div class="tts-action-row">
                <div class="tts-speed-box">
                  <div class="tts-speed-label">
                    <span>语速</span>
                    <strong>{{ ttsPlaybackRate.toFixed(1) }}x</strong>
                  </div>
                  <input
                    v-model.number="ttsPlaybackRate"
                    class="tts-speed-slider"
                    type="range"
                    min="0.5"
                    max="2"
                    step="0.1"
                  />
                </div>

                <button
                  type="button"
                  class="tts-try-button"
                  :disabled="!selectedTtsVoice"
                  @click="previewSelectedVoice"
                >
                  {{ ttsPreviewing ? '停止试听' : '试听' }}
                </button>
              </div>

              <div class="tts-selection-bar">
                <div>
                  <span>当前音色</span>
                  <strong>{{ ttsSelectedVoiceLabel }}</strong>
                </div>
                <div>
                  <span>voice code</span>
                  <code>{{ getVoiceCode(selectedTtsVoice) || '--' }}</code>
                </div>
                <button
                  type="button"
                  class="toolbar-button secondary tts-selection-action"
                  :disabled="!selectedTtsVoice"
                  @click="useSelectedVoiceForProject"
                >
                  用这个音色创建任务
                </button>
              </div>
            </article>
          </section>

          <section
            v-if="visitedDebugTabs.project"
            v-show="activeDebugTab === 'project'"
            class="debug-panel"
          >
            <article class="tts-lab project-lab">
              <div class="tts-lab-header">
                <div>
                  <p class="tts-caption">花生调试台</p>
                  <h2>创建任务</h2>
                  <p class="tts-description">先选择音色，再选择发布账号。创建任务后可单独点击导出按钮，系统会先设置字幕，再执行导出。</p>
                </div>
                <div class="project-header-actions">
                  <button
                    type="button"
                    class="toolbar-button secondary project-export-button"
                    :disabled="!projectCanExport"
                    @click="exportCurrentProject"
                  >
                    {{ projectSubtitleLoading ? '设置字幕...' : projectExportLoading ? '发起导出...' : projectExportPolling ? '导出中...' : '导出成片' }}
                  </button>
                  <button
                    type="button"
                    class="tts-primary-button project-create-button"
                    :disabled="!canCreateProject"
                    @click="createProjectTask"
                  >
                    {{ projectLoading ? '创建中...' : projectPolling ? '处理中...' : '发布创建任务' }}
                  </button>
                </div>
              </div>

              <div class="tts-account-strip">
                <div class="tts-account-card">
                  <span>当前 voice_id</span>
                  <strong>{{ projectForm.voiceId || '--' }}</strong>
                  <small>{{ selectedTtsVoice ? selectedTtsVoice.name : '未从音色页带入' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>发布账号</span>
                  <strong>{{ selectedProjectAccount ? maskPhone(selectedProjectAccount.phone) : '请选择账号' }}</strong>
                  <small>{{ selectedProjectAccount ? selectedProjectAccount.note || '未填写备注' : `可用账号池 ${debugAccountPool.length} 个` }}</small>
                </div>
                <div class="tts-account-card">
                  <span>任务响应</span>
                  <strong>{{ projectDisplayId }}</strong>
                  <small>pid {{ projectDisplayPid }} · {{ projectLastFetchAt || '等待创建' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>字幕设置</span>
                  <strong>{{ subtitleSettingsSummary }}</strong>
                  <small>{{ projectSubtitleResult ? '本次任务已应用字幕设置' : '导出前会自动应用已保存配置' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>当前状态</span>
                  <strong>{{ projectCurrentStageLabel }}</strong>
                  <small>{{ projectStatusSummary }}</small>
                </div>
                <div class="tts-account-card">
                  <span>项目进度</span>
                  <strong>{{ projectResult?.pid ? `${projectProgressValue}%` : '--' }}</strong>
                  <small>{{ projectStateText }} · 第 {{ projectPollCount || 0 }} 次</small>
                </div>
                <div class="tts-account-card">
                  <span>导出进度</span>
                  <strong>{{ projectExportTask?.task_id ? `${projectExportProgressValue}%` : '--' }}</strong>
                  <small>{{ projectExportStateText }} · 第 {{ projectExportPollCount || 0 }} 次</small>
                </div>
                <div class="tts-account-card">
                  <span>导出任务</span>
                  <strong>{{ projectExportTaskId }}</strong>
                  <small>version {{ projectExportVersion }}</small>
                </div>
              </div>

              <div class="project-form-grid">
                <label class="form-field project-field">
                  <span>发布账号</span>
                  <select v-model="projectForm.accountId">
                    <option value="">请选择发布账号</option>
                    <option
                      v-for="account in debugAccountPool"
                      :key="account.id"
                      :value="String(account.id)"
                    >
                      {{ account.phone }} · {{ account.note || '未填写备注' }}
                    </option>
                  </select>
                </label>

                <label class="form-field project-field">
                  <span>任务名称</span>
                  <input
                    v-model="projectForm.name"
                    type="text"
                    placeholder="可以留空，交给接口默认生成"
                  />
                </label>

                <label class="form-field project-field">
                  <span>voice_id</span>
                  <input
                    v-model.number="projectForm.voiceId"
                    type="number"
                    min="1"
                    readonly
                    placeholder="请点击下方选择音色"
                  />
                  <small class="project-field-hint">
                    {{ selectedTtsVoice ? `当前音色：${selectedTtsVoice.name}` : '当前还没有选中音色' }}
                  </small>
                </label>

                <label class="form-field project-field">
                  <span>speech_rate</span>
                  <input
                    v-model.number="projectForm.speechRate"
                    type="number"
                    min="0.1"
                    step="0.1"
                  />
                </label>
              </div>

              <div class="project-actions">
                <button
                  type="button"
                  class="toolbar-button secondary"
                  @click="openProjectVoicePicker"
                >
                  点击选择音色
                </button>
                <button
                  type="button"
                  class="toolbar-button secondary"
                  :disabled="!selectedTtsVoice"
                  @click="useSelectedVoiceForProject"
                >
                  使用当前音色
                </button>
                <button
                  type="button"
                  class="toolbar-button secondary"
                  @click="switchSection('settings')"
                >
                  设置字幕
                </button>
                <span class="project-hint">默认附带 `is_denoise=0`、`voice_type=0`、`project_type=0` 等固定参数，导出前会自动设置字幕。</span>
              </div>

              <label class="form-field project-field">
                <span>脚本文案</span>
                <textarea
                  v-model="projectForm.script"
                  rows="14"
                  placeholder="输入用于创建任务的完整文案"
                />
              </label>

              <div class="tts-selection-bar">
                <div>
                  <span>最近响应</span>
                  <strong>{{ projectResult ? `id ${projectDisplayId}` : '暂无返回结果' }}</strong>
                </div>
                <div>
                  <span>pid</span>
                  <code>{{ projectDisplayPid }}</code>
                </div>
                <div>
                  <span>项目状态</span>
                  <code>{{ projectStateText }}</code>
                </div>
                <div>
                  <span>导出状态</span>
                  <code>{{ projectExportStateText }}</code>
                </div>
                <div>
                  <span>字幕样式</span>
                  <code>{{ subtitleSettingsSummary }}</code>
                </div>
                <div class="project-result-actions">
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="!projectResult?.pid || projectLoading"
                    @click="refreshProjectProgress"
                  >
                    手动刷新状态
                  </button>
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="!projectViewUrl"
                    @click="copyProjectViewUrl"
                  >
                    复制成片链接
                  </button>
                  <button
                    type="button"
                    class="toolbar-button primary project-view-button"
                    :disabled="!projectCanView"
                    @click="openProjectView"
                  >
                    查看成片
                  </button>
                </div>
              </div>
            </article>
          </section>

          <section
            v-if="visitedDebugTabs.imageOcr"
            v-show="activeDebugTab === 'imageOcr'"
            class="debug-panel"
          >
            <article class="tts-lab model-debug-lab image-ocr-lab">
              <div class="tts-lab-header">
                <div>
                  <p class="tts-caption">OCR 调试台</p>
                  <h2>图片初审</h2>
                  <p class="tts-description">选择一张本地图片，使用 PaddleOCR 识别图片中的文本内容并直接展示结果。</p>
                </div>
                <div class="model-debug-actions">
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="imageOcrLoading || !desktopReady"
                    @click="chooseImageForOcr"
                  >
                    选择图片
                  </button>
                  <button
                    type="button"
                    class="tts-primary-button model-debug-run-button"
                    :disabled="imageOcrLoading || !desktopReady"
                    @click="runImageOcr"
                  >
                    {{ imageOcrLoading ? '识别中...' : '开始识别' }}
                  </button>
                </div>
              </div>

              <div class="tts-account-strip">
                <div class="tts-account-card">
                  <span>当前文件</span>
                  <strong>{{ imageOcrFileName }}</strong>
                  <small>{{ imageOcrForm.imagePath || '还没有选择图片' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>识别引擎</span>
                  <strong>{{ imageOcrResult?.engine || 'PaddleOCR' }}</strong>
                  <small>{{ imageOcrLoading ? '首次使用会下载并初始化 OCR 模型' : '支持 PNG/JPG/JPEG/BMP/WEBP/TIF/TIFF' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>识别结果</span>
                  <strong>{{ imageOcrResult ? `${Number(imageOcrResult.lineCount || 0)} 行` : '--' }}</strong>
                  <small>{{ imageOcrResult?.text ? `${imageOcrResult.text.length} 个字符` : '识别完成后会展示在下方' }}</small>
                </div>
              </div>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>图片路径</strong>
                  <small>点击按钮从本地选择一张待识别图片</small>
                </div>
                <div class="image-ocr-picker-row">
                  <label class="form-field image-ocr-path-field">
                    <span>本地图片</span>
                    <input
                      v-model="imageOcrForm.imagePath"
                      type="text"
                      readonly
                      placeholder="请选择一张图片"
                    />
                  </label>
                  <button
                    type="button"
                    class="toolbar-button secondary image-ocr-picker-button"
                    :disabled="imageOcrLoading || !desktopReady"
                    @click="chooseImageForOcr"
                  >
                    重新选择
                  </button>
                </div>
              </section>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>识别结果</strong>
                  <small>返回按行拼接后的纯文本内容</small>
                </div>
                <div v-if="imageOcrResult?.text" class="model-debug-result-card">
                  <pre class="model-debug-result">{{ imageOcrResult.text }}</pre>
                  <div class="model-debug-result-actions">
                    <span class="prompt-toolbar-meta">
                      {{ imageOcrResult.engine }} · {{ Number(imageOcrResult.lineCount || 0) }} 行
                    </span>
                    <button
                      type="button"
                      class="toolbar-button secondary"
                      @click="copyText(imageOcrResult.text)"
                    >
                      复制内容
                    </button>
                  </div>
                </div>
                <div v-else-if="imageOcrResult" class="tts-empty-state">
                  识别完成，但当前图片没有提取到文本。
                </div>
                <div v-else-if="imageOcrErrorMessage" class="tts-empty-state">
                  {{ imageOcrErrorMessage }}
                </div>
                <div v-else class="tts-empty-state">
                  还没有识别结果，先选择图片再点击“开始识别”。
                </div>
              </section>
            </article>
          </section>

          <section
            v-if="visitedDebugTabs.rewrite"
            v-show="activeDebugTab === 'rewrite'"
            class="debug-panel"
          >
            <article class="tts-lab model-debug-lab">
              <div class="tts-lab-header">
                <div>
                  <p class="tts-caption">模型调试台</p>
                  <h2>文章改写</h2>
                  <p class="tts-description">选择数据库里已保存的改写提示词，把文章内容直接发给模型并返回改写结果。</p>
                </div>
                <div class="model-debug-actions">
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="modelSettingsLoading || !desktopReady"
                    @click="loadModelSettings('模型设置已刷新到调试台')"
                  >
                    {{ modelSettingsLoading ? '加载中...' : '刷新模型设置' }}
                  </button>
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="!desktopReady"
                    @click="fillRewriteFormFromModelSettings"
                  >
                    从模型设置带入
                  </button>
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="rewriteConnectionLoading || rewriteLoading || !desktopReady"
                    @click="testRewriteModelConnection"
                  >
                    {{ rewriteConnectionLoading ? '测试中...' : '测试连接' }}
                  </button>
                  <button
                    type="button"
                    class="tts-primary-button model-debug-run-button"
                    :disabled="rewriteLoading || !desktopReady"
                    @click="rewriteArticleWithModel"
                  >
                    {{ rewriteLoading ? '改写中...' : '执行改写' }}
                  </button>
                </div>
              </div>

              <div class="tts-account-strip">
                <div class="tts-account-card">
                  <span>当前模型</span>
                  <strong>{{ rewriteForm.model || '--' }}</strong>
                  <small>{{ rewriteForm.baseUrl || '点击右上角带入或手动填写' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>提示词</span>
                  <strong>{{ selectedRewritePrompt ? `#${selectedRewritePrompt.id}` : '--' }}</strong>
                  <small>
                    {{
                      selectedRewritePrompt
                        ? selectedRewritePrompt.content
                        : `数据库已保存 ${persistedRewritePromptCount} 条改写提示词`
                    }}
                  </small>
                </div>
                <div class="tts-account-card">
                  <span>输出结果</span>
                  <strong>{{ rewriteResult?.content ? `${rewriteResult.content.length} 字` : '--' }}</strong>
                  <small>{{ rewriteLoading ? '模型正在处理中' : '改写完成后会展示在下方' }}</small>
                </div>
              </div>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>模型参数</strong>
                  <small>支持直接覆盖设置页里保存的模型参数</small>
                </div>
                <div class="settings-form-grid">
                  <label class="form-field">
                    <span>Base URL</span>
                    <input
                      v-model="rewriteForm.baseUrl"
                      type="text"
                      placeholder="例如 https://api.openai.com/v1"
                    />
                  </label>
                  <label class="form-field">
                    <span>API Key</span>
                    <input
                      v-model="rewriteForm.apiKey"
                      type="password"
                      placeholder="输入模型接口的 API Key"
                    />
                  </label>
                  <label class="form-field">
                    <span>Model</span>
                    <input
                      v-model="rewriteForm.model"
                      type="text"
                      placeholder="例如 gpt-5.4"
                    />
                  </label>
                </div>
              </section>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>改写提示词</strong>
                  <small>这里只显示数据库里已经保存的提示词，调用时会传提示词 ID</small>
                </div>
                <div v-if="persistedRewritePrompts.length" class="model-debug-prompt-grid">
                  <button
                    v-for="prompt in persistedRewritePrompts"
                    :key="prompt.id"
                    type="button"
                    class="model-debug-prompt-card"
                    :data-active="String(rewriteForm.promptId) === String(prompt.id)"
                    @click="selectRewritePrompt(prompt)"
                  >
                    <strong>提示词 #{{ prompt.id }}</strong>
                    <span>{{ prompt.content }}</span>
                  </button>
                </div>
                <div v-else class="tts-empty-state">
                  当前数据库里还没有已保存的改写提示词，请先到设置页保存提示词。
                </div>
              </section>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>原始文章</strong>
                  <small>把要改写的文章粘贴到这里</small>
                </div>
                <label class="form-field">
                  <textarea
                    v-model="rewriteForm.article"
                    rows="14"
                    placeholder="输入需要改写的文章内容"
                  />
                </label>
              </section>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>改写结果</strong>
                  <small>返回的是模型输出的纯文本结果</small>
                </div>
                <div v-if="rewriteResult?.content" class="model-debug-result-card">
                  <pre class="model-debug-result">{{ rewriteResult.content }}</pre>
                  <div class="model-debug-result-actions">
                    <span class="prompt-toolbar-meta">
                      提示词 #{{ rewriteResult.promptId }} · {{ rewriteResult.model }}
                    </span>
                    <button
                      type="button"
                      class="toolbar-button secondary"
                      @click="copyText(rewriteResult.content)"
                    >
                      复制结果
                    </button>
                  </div>
                </div>
                <div v-else-if="rewriteErrorMessage" class="tts-empty-state">
                  {{ rewriteErrorMessage }}
                </div>
                <div v-else class="tts-empty-state">
                  还没有改写结果，填好参数后点击“执行改写”。
                </div>
              </section>
            </article>
          </section>

          <section
            v-if="visitedDebugTabs.title"
            v-show="activeDebugTab === 'title'"
            class="debug-panel"
          >
            <article class="tts-lab model-debug-lab">
              <div class="tts-lab-header">
                <div>
                  <p class="tts-caption">模型调试台</p>
                  <h2>标题生成</h2>
                  <p class="tts-description">把文章正文和标题提示词发给模型，直接返回生成标题。</p>
                </div>
                <div class="model-debug-actions">
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="modelSettingsLoading || !desktopReady"
                    @click="loadModelSettings('模型设置已刷新到调试台')"
                  >
                    {{ modelSettingsLoading ? '加载中...' : '刷新模型设置' }}
                  </button>
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="!desktopReady"
                    @click="fillTitleFormFromModelSettings"
                  >
                    从模型设置带入
                  </button>
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="titleConnectionLoading || titleLoading || !desktopReady"
                    @click="testTitleModelConnection"
                  >
                    {{ titleConnectionLoading ? '测试中...' : '测试连接' }}
                  </button>
                  <button
                    type="button"
                    class="tts-primary-button model-debug-run-button"
                    :disabled="titleLoading || !desktopReady"
                    @click="generateTitleWithModel"
                  >
                    {{ titleLoading ? '生成中...' : '执行生成' }}
                  </button>
                </div>
              </div>

              <div class="tts-account-strip">
                <div class="tts-account-card">
                  <span>当前模型</span>
                  <strong>{{ titleForm.model || '--' }}</strong>
                  <small>{{ titleForm.baseUrl || '点击右上角带入或手动填写' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>标题提示词</span>
                  <strong>{{ titleForm.titlePrompt ? `${titleForm.titlePrompt.length} 字` : '--' }}</strong>
                  <small>{{ titleForm.titlePrompt || '优先从模型设置页带入，也可单独修改' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>生成标题</span>
                  <strong>{{ titleResult?.title || '--' }}</strong>
                  <small>{{ titleLoading ? '模型正在处理中' : '生成完成后会展示在下方' }}</small>
                </div>
              </div>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>模型参数</strong>
                  <small>支持直接覆盖设置页里保存的模型参数</small>
                </div>
                <div class="settings-form-grid">
                  <label class="form-field">
                    <span>Base URL</span>
                    <input
                      v-model="titleForm.baseUrl"
                      type="text"
                      placeholder="例如 https://api.openai.com/v1"
                    />
                  </label>
                  <label class="form-field">
                    <span>API Key</span>
                    <input
                      v-model="titleForm.apiKey"
                      type="password"
                      placeholder="输入模型接口的 API Key"
                    />
                  </label>
                  <label class="form-field">
                    <span>Model</span>
                    <input
                      v-model="titleForm.model"
                      type="text"
                      placeholder="例如 gpt-5.4"
                    />
                  </label>
                </div>
              </section>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>标题提示词</strong>
                  <small>这里直接传入标题提示词字符串</small>
                </div>
                <label class="form-field">
                  <textarea
                    v-model="titleForm.titlePrompt"
                    rows="5"
                    placeholder="输入用于生成标题的提示词"
                  />
                </label>
              </section>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>原始文章</strong>
                  <small>把要生成标题的文章粘贴到这里</small>
                </div>
                <label class="form-field">
                  <textarea
                    v-model="titleForm.article"
                    rows="14"
                    placeholder="输入需要生成标题的文章内容"
                  />
                </label>
              </section>

              <section class="settings-block">
                <div class="settings-block-head">
                  <strong>生成结果</strong>
                  <small>返回的是模型生成的标题文本</small>
                </div>
                <div v-if="titleResult?.title" class="model-debug-result-card">
                  <pre class="model-debug-result">{{ titleResult.title }}</pre>
                  <div class="model-debug-result-actions">
                    <span class="prompt-toolbar-meta">{{ titleResult.model }}</span>
                    <button
                      type="button"
                      class="toolbar-button secondary"
                      @click="copyText(titleResult.title)"
                    >
                      复制标题
                    </button>
                  </div>
                </div>
                <div v-else-if="titleErrorMessage" class="tts-empty-state">
                  {{ titleErrorMessage }}
                </div>
                <div v-else class="tts-empty-state">
                  还没有生成结果，填好参数后点击“执行生成”。
                </div>
              </section>
            </article>
          </section>
        </div>
      </section>

      <section
        v-if="visitedSections.settings"
        v-show="activeSection === 'settings'"
        class="page-body settings-page"
      >
        <div class="settings-shell">
          <div class="settings-tabs" role="tablist" aria-label="Settings tabs">
            <button
              v-for="tab in settingsTabs"
              :key="tab.key"
              type="button"
              class="settings-tab"
              :data-active="activeSettingsTab === tab.key"
              @click="activateSettingsTab(tab.key)"
            >
              <strong>{{ tab.label }}</strong>
              <small>{{ tab.description }}</small>
            </button>
          </div>

          <article
            v-if="visitedSettingsTabs.global"
            v-show="activeSettingsTab === 'global'"
            class="tts-lab settings-panel"
          >
            <div class="tts-lab-header">
              <div>
                <p class="tts-caption">全局设置</p>
                <h2>后台任务线程池</h2>
                <p class="tts-description">应用启动后会每 5 秒扫描一次任务列表。S1 负责文章改写，S2 负责标题生成，这里的线程池大小会直接影响并发处理数量。</p>
              </div>
              <div class="settings-toolbar">
                <button
                  type="button"
                  class="toolbar-button secondary"
                  :disabled="globalSettingsLoading || !desktopReady"
                  @click="loadGlobalSettings('全局设置已刷新')"
                >
                  {{ globalSettingsLoading ? '刷新中...' : '从数据库刷新' }}
                </button>
                <button
                  type="button"
                  class="tts-primary-button settings-save-button"
                  :disabled="globalSettingsSaving || globalSettingsLoading || !desktopReady"
                  @click="saveGlobalSettings"
                >
                  {{ globalSettingsSaving ? '保存中...' : '保存全局设置' }}
                </button>
              </div>
            </div>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>线程池大小</strong>
                <small>用于后台 S1 改写和 S2 标题生成的并发数量</small>
              </div>
              <div class="settings-form-grid global-settings-grid">
                <label class="form-field">
                  <span>线程池大小</span>
                  <input
                    v-model.number="globalSettings.threadPoolSize"
                    type="number"
                    min="1"
                    max="32"
                    step="1"
                    placeholder="请输入 1 到 32"
                  />
                </label>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>默认下载路径</strong>
                <small>任务列表里点击下载后，会保存到这里，成功后自动删除对应任务</small>
              </div>
              <div class="download-directory-picker">
                <label class="form-field download-directory-field">
                  <span>下载文件夹</span>
                  <input
                    :value="globalSettings.downloadDir"
                    type="text"
                    readonly
                    placeholder="请选择默认下载目录"
                  />
                </label>
                <div class="download-directory-actions">
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="globalSettingsLoading || globalSettingsSaving || !desktopReady"
                    @click="chooseGlobalDownloadDirectory"
                  >
                    选择文件夹
                  </button>
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="globalSettingsLoading || globalSettingsSaving"
                    @click="clearGlobalDownloadDirectory"
                  >
                    清空
                  </button>
                </div>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>S4 封面审核</strong>
                <small>项目处理完成后，可选地对每个 clip 封面做 OCR，识别到网址时直接判定任务失败</small>
              </div>
              <div class="settings-form-grid global-settings-grid">
                <label class="form-field">
                  <span>是否判断网址</span>
                  <select v-model="globalSettings.checkWebsiteLinks">
                    <option :value="true">开启</option>
                    <option :value="false">关闭</option>
                  </select>
                </label>
              </div>
            </section>

            <section class="settings-block">
              <div class="tts-account-strip voice-settings-strip">
                <div class="tts-account-card">
                  <span>当前线程池</span>
                  <strong>{{ normalizeGlobalThreadPoolSize(globalSettings.threadPoolSize) }}</strong>
                  <small>建议按模型接口吞吐和机器性能调整</small>
                </div>
                <div class="tts-account-card">
                  <span>扫描频率</span>
                  <strong>5 秒</strong>
                  <small>应用启动后自动持续扫描任务列表</small>
                </div>
                <div class="tts-account-card">
                  <span>下载目录</span>
                  <strong>{{ getPathTail(globalSettings.downloadDir) }}</strong>
                  <small>{{ globalSettings.downloadDir || '还没有保存默认下载路径' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>网址审核</span>
                  <strong>{{ normalizeGlobalCheckWebsiteLinks(globalSettings.checkWebsiteLinks) ? '开启' : '关闭' }}</strong>
                  <small>{{ normalizeGlobalCheckWebsiteLinks(globalSettings.checkWebsiteLinks) ? 'S4 完成后会先做封面 OCR 链接检查' : '当前不会执行封面 OCR 链接检查' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>当前版本</span>
                  <strong>{{ displayAppVersion }}</strong>
                  <small>版本号由桌面后端统一提供</small>
                </div>
                <div class="tts-account-card">
                  <span>最近保存</span>
                  <strong>{{ globalSettingsLastSavedAt || '--' }}</strong>
                  <small>{{ globalSettingsSummary }}</small>
                </div>
              </div>
            </section>
          </article>

          <article
            v-if="visitedSettingsTabs.huasheng"
            v-show="activeSettingsTab === 'huasheng'"
            class="tts-lab settings-panel"
          >
            <div class="tts-lab-header">
              <div>
                <p class="tts-caption">花生设置</p>
                <h2>字幕与音色</h2>
                <p class="tts-description">这里保存的是导出前会自动应用到花生项目里的字幕配置，以及默认音色和语速。</p>
              </div>
              <div class="settings-toolbar">
                <button
                  type="button"
                  class="toolbar-button secondary"
                  :disabled="subtitleSettingsLoading || !desktopReady"
                  @click="loadSubtitleSettings('字幕设置已刷新')"
                >
                  {{ subtitleSettingsLoading ? '刷新中...' : '从数据库刷新' }}
                </button>
                <button
                  type="button"
                  class="tts-primary-button settings-save-button"
                  :disabled="subtitleSettingsSaving || subtitleSettingsLoading || !desktopReady"
                  @click="saveSubtitleSettings"
                >
                  {{ subtitleSettingsSaving ? '保存中...' : '保存字幕设置' }}
                </button>
              </div>
            </div>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>字号设置</strong>
                <small>导出前会自动同步到字幕配置</small>
              </div>
              <div class="subtitle-size-grid">
                <button
                  v-for="option in subtitleFontSizeOptions"
                  :key="option.value"
                  type="button"
                  class="subtitle-size-button"
                  :data-active="subtitleSettings.fontSize === option.value"
                  @click="selectSubtitleFontSize(option)"
                >
                  <strong>{{ option.label }}</strong>
                  <small>{{ option.value }}</small>
                </button>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>字幕样式</strong>
                <small>按花生原界面的字形方式选择描边样式</small>
              </div>
              <div class="subtitle-style-strip" role="list" aria-label="字幕样式">
                <button
                  v-for="style in subtitleStyleOptions"
                  :key="style.id"
                  type="button"
                  class="subtitle-style-option"
                  :data-active="subtitleSettings.styleId === style.id"
                  :title="style.label"
                  @click="selectSubtitleStyle(style)"
                >
                  <svg
                    class="subtitle-style-icon"
                    viewBox="0 0 21 23"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                  >
                    <path
                      fill-rule="evenodd"
                      clip-rule="evenodd"
                      d="M19.6227 1H1V4.3213H8.39534V21.0547H12.2274V4.3213H19.6227V1Z"
                      :fill="style.fontColor"
                    />
                    <path
                      d="M1 1V0H0V1H1ZM19.6227 1H20.6227V0H19.6227V1ZM1 4.3213H0V5.3213H1V4.3213ZM8.39534 4.3213H9.39534V3.3213H8.39534V4.3213ZM8.39534 21.0547H7.39534V22.0547H8.39534V21.0547ZM12.2274 21.0547V22.0547H13.2274V21.0547H12.2274ZM12.2274 4.3213V3.3213H11.2274V4.3213H12.2274ZM19.6227 4.3213V5.3213H20.6227V4.3213H19.6227ZM1 2H19.6227V0H1V2ZM2 4.3213V1H0V4.3213H2ZM8.39534 3.3213H1V5.3213H8.39534V3.3213ZM9.39534 21.0547V4.3213H7.39534V21.0547H9.39534ZM12.2274 20.0547H8.39534V22.0547H12.2274V20.0547ZM11.2274 4.3213V21.0547H13.2274V4.3213H11.2274ZM19.6227 3.3213H12.2274V5.3213H19.6227V3.3213ZM18.6227 1V4.3213H20.6227V1H18.6227Z"
                      :fill="style.outlineColor"
                    />
                  </svg>
                </button>
              </div>
              <div class="subtitle-style-summary">
                <span>当前已选</span>
                <strong>{{ selectedSubtitleStyle?.label || '未选择样式' }}</strong>
                <code>{{ subtitleSettings.fontColor }} / {{ subtitleSettings.outlineColor }} / {{ subtitleSettings.outlineThick }}</code>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>音色设置</strong>
                <small>点击设置音色后会拉取最新音色列表，可试听并把音色、语速和单账号并发数一起保存到数据库</small>
              </div>
              <div class="settings-form-grid">
                <label class="form-field">
                  <span>单账号并发任务数</span>
                  <input
                    v-model.number="huashengVoiceSettings.maxConcurrentTasksPerAccount"
                    type="number"
                    min="1"
                    max="50"
                    step="1"
                    placeholder="请输入 1 到 50"
                  />
                </label>
              </div>
              <div class="tts-account-strip voice-settings-strip">
                <div class="tts-account-card">
                  <span>当前音色</span>
                  <strong>{{ huashengVoiceSettings.voiceName || '未设置默认音色' }}</strong>
                  <small>
                    {{
                      huashengVoiceSettings.voiceTags ||
                      (huashengVoiceSettings.voiceId ? `音色 ID ${huashengVoiceSettings.voiceId}` : '点击下方按钮开始设置')
                    }}
                  </small>
                </div>
                <div class="tts-account-card">
                  <span>当前语速</span>
                  <strong>{{ Number(huashengVoiceSettings.speechRate || 1).toFixed(1) }}x</strong>
                  <small>{{ huashengVoiceSettings.voiceCode || '未保存 voice code' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>单账号并发</span>
                  <strong>{{ normalizeHuashengMaxConcurrentTasks(huashengVoiceSettings.maxConcurrentTasksPerAccount) }}</strong>
                  <small>同一花生账号同时运行的任务上限</small>
                </div>
                <div class="tts-account-card">
                  <span>最近保存</span>
                  <strong>{{ huashengVoiceLastSavedAt || '--' }}</strong>
                  <small>{{ huashengVoiceSummary }}</small>
                </div>
              </div>
              <div class="voice-settings-actions">
                <button
                  type="button"
                  class="toolbar-button secondary"
                  :disabled="huashengVoiceSettingsLoading || !desktopReady"
                  @click="loadHuashengVoiceSettings('音色设置已刷新')"
                >
                  {{ huashengVoiceSettingsLoading ? '刷新中...' : '从数据库刷新' }}
                </button>
                <button
                  type="button"
                  class="tts-primary-button settings-save-button"
                  :disabled="huashengVoiceSettingsSaving || huashengVoiceSettingsLoading || !desktopReady"
                  @click="saveHuashengVoiceSettings"
                >
                  {{ huashengVoiceSettingsSaving ? '保存中...' : '保存花生设置' }}
                </button>
                <button
                  type="button"
                  class="toolbar-button secondary"
                  :disabled="huashengVoiceSettingsSaving || ttsLoading || !desktopReady"
                  @click="openSettingsVoicePicker"
                >
                  {{ huashengVoiceSettingsSaving ? '保存中...' : '设置音色' }}
                </button>
              </div>
            </section>
          </article>

          <article
            v-if="visitedSettingsTabs.ocr"
            v-show="activeSettingsTab === 'ocr'"
            class="tts-lab settings-panel"
          >
            <div class="tts-lab-header">
              <div>
                <p class="tts-caption">OCR 设置</p>
                <h2>模型检查与下载</h2>
                <p class="tts-description">这里专门处理 PaddleOCR 的本地模型状态。检查只做依赖、缓存和校验记录判断；下载才会真正触发模型初始化。</p>
              </div>
              <div class="settings-toolbar">
                <button
                  type="button"
                  class="toolbar-button secondary"
                  :disabled="ocrModelStatusLoading || ocrModelDownloadLoading || !desktopReady"
                  @click="loadOcrModelStatus('OCR 模型状态已刷新')"
                >
                  {{ ocrModelStatusLoading ? '检查中...' : '检查模型' }}
                </button>
                <button
                  type="button"
                  class="tts-primary-button settings-save-button"
                  :disabled="ocrModelDownloadLoading || ocrModelStatusLoading || !desktopReady"
                  @click="downloadOcrModel"
                >
                  {{ ocrModelDownloadLoading ? '下载中...' : '下载模型' }}
                </button>
              </div>
            </div>

            <section class="settings-block">
              <div class="tts-account-strip voice-settings-strip">
                <div class="tts-account-card">
                  <span>当前引擎</span>
                  <strong>{{ ocrModelStatus?.engine || 'PaddleOCR' }}</strong>
                  <small>{{ ocrModelStatus?.message || '点击右上角检查模型状态' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>模型状态</span>
                  <strong>{{ ocrModelStatus?.ready ? '已就绪' : '未就绪' }}</strong>
                  <small>{{ ocrModelStatus?.status || '尚未检查' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>缓存体积</span>
                  <strong>{{ formatByteSize(ocrModelStatus?.cacheSizeBytes) }}</strong>
                  <small>{{ ocrModelStatus ? `${Number(ocrModelStatus.artifactFileCount || 0)} 个模型文件` : '尚未检查' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>校验记录</span>
                  <strong>{{ ocrModelStatus?.verified ? '已验证' : '未验证' }}</strong>
                  <small>{{ ocrModelStatus?.verifiedAt || '还没有成功校验记录' }}</small>
                </div>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>缓存目录</strong>
                <small>OCR 模型会缓存到数据库同级目录下的 `.paddle-cache/paddlex`</small>
              </div>
              <div class="tts-account-strip voice-settings-strip">
                <div class="tts-account-card">
                  <span>缓存路径</span>
                  <strong>{{ getPathTail(ocrModelStatus?.cacheDir) }}</strong>
                  <small>{{ ocrModelStatus?.cacheDir || '尚未检查' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>目录可写</span>
                  <strong>{{ ocrModelStatus?.cacheWritable ? '可写' : '不可写' }}</strong>
                  <small>{{ ocrModelStatus?.cacheWritableMessage || '尚未检查' }}</small>
                </div>
                <div class="tts-account-card">
                  <span>模型目录数</span>
                  <strong>{{ ocrModelStatus ? Number(ocrModelStatus.artifactDirectoryCount || 0) : '--' }}</strong>
                  <small>{{ ocrModelStatus?.engineInitialized ? '本进程已经完成初始化' : '当前进程还没有初始化引擎' }}</small>
                </div>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>依赖检查</strong>
                <small>会检查 `paddleocr`、`paddlepaddle` 和 `paddlex` 是否安装且可导入</small>
              </div>
              <div class="tts-account-strip voice-settings-strip">
                <div
                  v-for="item in ocrModelStatus?.dependencyItems || []"
                  :key="item.module"
                  class="tts-account-card"
                >
                  <span>{{ item.package }}</span>
                  <strong>{{ item.importable ? '可用' : item.installed ? '导入失败' : '未安装' }}</strong>
                  <small>{{ item.errorMessage || item.module }}</small>
                </div>
              </div>
            </section>

            <section v-if="(ocrModelStatus?.sampleFiles || []).length" class="settings-block">
              <div class="settings-block-head">
                <strong>模型文件示例</strong>
                <small>这里只展示前几条命中的模型文件，便于确认缓存是否已经落地</small>
              </div>
              <div class="tts-empty-state">
                <div
                  v-for="path in ocrModelStatus.sampleFiles"
                  :key="path"
                >
                  {{ path }}
                </div>
              </div>
            </section>
          </article>

          <MicroheadlineSettingsPanel
            v-if="visitedSettingsTabs.microheadline"
            v-show="activeSettingsTab === 'microheadline'"
            :desktop-ready="desktopReady"
            @status="statusMessage = $event"
            @database-path="databasePath = $event"
          />

          <article
            v-if="visitedSettingsTabs.model"
            v-show="activeSettingsTab === 'model'"
            class="tts-lab settings-panel"
          >
            <div class="tts-lab-header">
              <div>
                <p class="tts-caption">模型设置</p>
                <h2>模型与提示词</h2>
                <p class="tts-description">这里管理改写模型的接口参数、标题提示词，以及可维护的改写提示词列表。提示词默认可以为空。</p>
              </div>
                <div class="settings-toolbar">
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="modelSettingsLoading || !desktopReady"
                    @click="loadModelSettings('模型设置已刷新')"
                  >
                    {{ modelSettingsLoading ? '刷新中...' : '从数据库刷新' }}
                  </button>
                  <button
                    type="button"
                    class="toolbar-button secondary"
                    :disabled="modelConnectionLoading || !desktopReady"
                    @click="testSavedModelConnection"
                  >
                    {{ modelConnectionLoading ? '测试中...' : '测试连接' }}
                  </button>
                  <button
                    type="button"
                    class="tts-primary-button settings-save-button"
                    :disabled="modelSettingsSaving || modelSettingsLoading || !desktopReady"
                    @click="saveModelSettings"
                >
                  {{ modelSettingsSaving ? '保存中...' : '保存模型设置' }}
                </button>
              </div>
            </div>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>模型参数</strong>
                <small>用于配置改写模型请求信息</small>
              </div>
              <div class="settings-form-grid">
                <label class="form-field">
                  <span>Base URL</span>
                  <input
                    v-model="modelSettings.baseUrl"
                    type="text"
                    placeholder="例如 https://api.openai.com/v1"
                  />
                </label>
                <label class="form-field">
                  <span>API Key</span>
                  <input
                    v-model="modelSettings.apiKey"
                    type="password"
                    placeholder="输入模型接口的 API Key"
                  />
                </label>
                <label class="form-field">
                  <span>Model</span>
                  <input
                    v-model="modelSettings.model"
                    type="text"
                    placeholder="例如 gpt-5.4"
                  />
                </label>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>标题提示词</strong>
                <small>这个字段与改写提示词列表分开保存</small>
              </div>
              <label class="form-field">
                <span>单独标题提示词</span>
                <textarea
                  v-model="modelSettings.titlePrompt"
                  rows="5"
                  placeholder="输入标题专用提示词，默认可留空"
                />
              </label>
            </section>

            <section class="settings-block">
              <div class="settings-block-head">
                <strong>改写提示词列表</strong>
                <small>每条提示词都会单独存进数据库表，默认可以为空</small>
              </div>
              <div class="prompt-toolbar">
                <button
                  type="button"
                  class="toolbar-button secondary"
                  @click="addRewritePrompt"
                >
                  添加提示词
                </button>
                <span class="prompt-toolbar-meta">当前 {{ rewritePromptCount }} 条</span>
              </div>

              <div v-if="rewritePrompts.length" class="prompt-list">
                <article
                  v-for="(prompt, index) in rewritePrompts"
                  :key="prompt.id"
                  class="prompt-card"
                >
                  <div class="prompt-card-head">
                    <strong>改写提示词 {{ index + 1 }}</strong>
                    <button
                      type="button"
                      class="toolbar-button secondary prompt-delete-button"
                      @click="removeRewritePrompt(prompt.id)"
                    >
                      删除
                    </button>
                  </div>
                  <label class="form-field">
                    <span>内容</span>
                    <textarea
                      v-model="prompt.content"
                      rows="5"
                      placeholder="输入这条改写提示词的内容，留空则保存时自动忽略"
                    />
                  </label>
                </article>
              </div>
              <div v-else class="tts-empty-state">
                当前还没有改写提示词，点击上方“添加提示词”即可新增。
              </div>
            </section>
          </article>
        </div>
      </section>

      <div
        v-if="taskStatusDialogOpen"
        class="dialog-backdrop"
        @click.self="closeTaskStatusDialog"
      >
        <section
          class="account-dialog task-status-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="task-status-dialog-title"
        >
          <div class="panel-head">
            <div>
              <p class="panel-kicker">任务统计</p>
              <h3 id="task-status-dialog-title">状态查看</h3>
            </div>
            <button
              type="button"
              class="toolbar-button secondary"
              @click="closeTaskStatusDialog"
            >
              关闭
            </button>
          </div>

          <div class="task-status-summary-section">
            <div class="task-status-summary-head">
              <strong>任务状态</strong>
              <small>总任务 {{ taskCount }}</small>
            </div>
            <div v-if="taskStatusCounts.length" class="task-status-summary-grid">
              <article
                v-for="item in taskStatusCounts"
                :key="`task-status-${item.label}`"
                class="task-status-summary-card"
              >
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
              </article>
            </div>
            <div v-else class="empty-inline">当前还没有任务记录</div>
          </div>

          <div class="task-status-summary-section">
            <div class="task-status-summary-head">
              <strong>花生状态</strong>
              <small>按花生接口同步结果统计</small>
            </div>
            <div v-if="taskHuashengStatusCounts.length" class="task-status-summary-grid">
              <article
                v-for="item in taskHuashengStatusCounts"
                :key="`huasheng-status-${item.label}`"
                class="task-status-summary-card"
              >
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
              </article>
            </div>
            <div v-else class="empty-inline">当前还没有花生状态数据</div>
          </div>
        </section>
      </div>

      <div
        v-if="taskDeleteDialogOpen"
        class="dialog-backdrop"
        @click.self="closeTaskDeleteDialog"
      >
        <section
          class="account-dialog task-delete-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="task-delete-dialog-title"
        >
          <div class="panel-head">
            <div>
              <p class="panel-kicker">任务管理</p>
              <h3 id="task-delete-dialog-title">删除全部任务</h3>
            </div>
            <button
              type="button"
              class="toolbar-button secondary"
              :disabled="taskDeleteLoading"
              @click="closeTaskDeleteDialog"
            >
              取消
            </button>
          </div>

          <div class="task-delete-dialog__summary">
            <strong>{{ taskCount }}</strong>
            <span>当前任务总数，删除后不可恢复</span>
          </div>

          <p class="task-delete-dialog__note">
            会清空任务列表里的全部记录，后台正在扫描的任务也不会再回写结果。
          </p>

          <div class="panel-actions task-delete-dialog__actions">
            <button
              type="button"
              class="toolbar-button danger"
              :disabled="taskDeleteLoading"
              @click="deleteAllTaskRecords"
            >
              {{ taskDeleteLoading ? '删除中...' : `确认删除 ${taskCount} 条任务` }}
            </button>
          </div>
        </section>
      </div>

      <div
        v-if="voicePickerDialogOpen"
        class="dialog-backdrop"
        @click.self="closeVoicePicker"
      >
        <section
          class="voice-picker-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="voice-picker-dialog-title"
        >
          <article class="tts-lab voice-picker-panel">
            <div class="tts-lab-header">
              <div>
                <p class="tts-caption">{{ voicePickerCaption }}</p>
                <h2 id="voice-picker-dialog-title">{{ voicePickerTitle }}</h2>
                <p class="tts-description">{{ voicePickerDescription }}</p>
              </div>
              <div class="voice-picker-toolbar">
                <button
                  type="button"
                  class="toolbar-button secondary tts-refresh-button"
                  :disabled="ttsLoading"
                  @click="fetchTtsVoices('音色选择弹窗已刷新', { preferredVoiceId: selectedTtsVoiceId })"
                >
                  {{ ttsLoading ? '加载中...' : '随机账号刷新' }}
                </button>
                <button
                  type="button"
                  class="toolbar-button secondary"
                  @click="closeVoicePicker"
                >
                  关闭
                </button>
              </div>
            </div>

            <div class="tts-account-strip">
              <div class="tts-account-card">
                <span>当前音色</span>
                <strong>{{ selectedTtsVoice ? selectedTtsVoice.name : '尚未选择音色' }}</strong>
                <small>
                  {{
                    selectedTtsVoice
                      ? getVoiceTags(selectedTtsVoice)
                      : voicePickerTarget === 'settings'
                        ? '点击下方卡片并保存到数据库'
                        : '点击下方卡片选择'
                  }}
                </small>
              </div>
              <div class="tts-account-card">
                <span>随机账号</span>
                <strong>{{ ttsLastFetchAccount ? maskPhone(ttsLastFetchAccount.phone) : '尚未发起请求' }}</strong>
                <small>
                  {{
                    ttsLastFetchAccount
                      ? ttsLastFetchAccount.note || '未填写备注'
                      : `可用账号池 ${debugAccountPool.length} 个`
                  }}
                </small>
              </div>
              <div class="tts-account-card">
                <span>最近同步</span>
                <strong>{{ ttsLastFetchAt || '--' }}</strong>
                <small>总数 {{ ttsPage?.total || ttsMaterials.length }} · 上次使用 {{ ttsLastUsedVoiceId || '--' }}</small>
              </div>
            </div>

            <div class="tts-category-tabs">
              <button
                v-for="category in ttsCategoryOptions"
                :key="category.id"
                type="button"
                class="tts-category-tab"
                :data-active="ttsRequest.categoryId === category.id"
                @click="changeTtsCategory(category.id)"
              >
                {{ category.title }}
              </button>
            </div>

            <div v-if="ttsMaterials.length" class="voice-picker-grid">
              <button
                v-for="voice in ttsMaterials"
                :key="voice.id"
                type="button"
                class="tts-voice-card"
                :data-active="String(selectedTtsVoiceId) === String(voice.id)"
                @click="selectTtsVoice(voice)"
              >
                <span
                  v-if="String(voice.id) === ttsLastUsedVoiceId"
                  class="tts-last-used-badge"
                >
                  上次使用
                </span>
                <div class="tts-voice-cover-wrap">
                  <img
                    v-if="voice.cover"
                    class="tts-voice-cover"
                    :src="voice.cover"
                    :alt="voice.name"
                  />
                  <div v-else class="tts-voice-cover tts-voice-cover-placeholder">
                    {{ voice.name.slice(0, 1) }}
                  </div>
                </div>
                <div class="tts-voice-copy">
                  <strong>{{ voice.name }}</strong>
                  <span>{{ getVoiceTags(voice) }}</span>
                </div>
              </button>
            </div>

            <div v-else class="tts-empty-state">
              {{ ttsLoading ? '正在加载公共音色...' : '还没有音色数据，点击右上角随机账号刷新。' }}
            </div>

            <div class="tts-action-row">
              <div class="tts-speed-box">
                <div class="tts-speed-label">
                  <span>语速</span>
                  <strong>{{ ttsPlaybackRate.toFixed(1) }}x</strong>
                </div>
                <input
                  v-model.number="ttsPlaybackRate"
                  class="tts-speed-slider"
                  type="range"
                  min="0.5"
                  max="2"
                  step="0.1"
                />
              </div>

              <button
                type="button"
                class="tts-try-button"
                :disabled="!selectedTtsVoice"
                @click="previewSelectedVoice"
              >
                {{ ttsPreviewing ? '停止试听' : '试听' }}
              </button>

              <button
                type="button"
                class="tts-primary-button voice-picker-apply-button"
                :disabled="!selectedTtsVoice || huashengVoiceSettingsSaving"
                @click="voicePickerTarget === 'settings' ? saveHuashengVoiceSettingsFromSelection() : useSelectedVoiceForProject()"
              >
                {{ huashengVoiceSettingsSaving ? '保存中...' : voicePickerApplyLabel }}
              </button>
            </div>
          </article>
        </section>
      </div>

      <div
        v-if="accountDialogOpen"
        class="dialog-backdrop"
        @click.self="closeAccountDialog"
      >
        <section
          class="account-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="account-dialog-title"
        >
          <div class="panel-head">
            <div>
              <p class="panel-kicker">{{ isEditing ? '编辑账号' : '新增账号' }}</p>
              <h3 id="account-dialog-title">{{ isEditing ? '修改花生账号' : '添加花生账号' }}</h3>
            </div>
            <button
              type="button"
              class="toolbar-button secondary"
              @click="closeAccountDialog"
            >
              取消
            </button>
          </div>

          <form class="account-form" @submit.prevent="submitForm">
            <label class="form-field">
              <span>手机号</span>
              <input
                v-model="form.phone"
                type="text"
                inputmode="numeric"
                placeholder="请输入 11 位手机号"
              />
            </label>

            <label class="form-field">
              <span>备注</span>
              <input
                v-model="form.note"
                type="text"
                placeholder="例如：主账号 / 素材号 / 已验证"
              />
            </label>

            <label class="form-field">
              <span>Cookies</span>
              <textarea
                v-model="form.cookies"
                rows="8"
                placeholder="粘贴完整 Cookies 字符串"
              />
            </label>

            <label class="toggle-field">
              <input v-model="form.isDisabled" type="checkbox" />
              <span>将该账号标记为禁用</span>
            </label>

            <div class="form-actions">
              <button
                type="button"
                class="toolbar-button secondary"
                @click="closeAccountDialog"
              >
                取消
              </button>
              <button type="submit" class="toolbar-button primary" :disabled="saving">
                {{ saving ? '提交中...' : isEditing ? '保存修改' : '添加账号' }}
              </button>
            </div>
          </form>
        </section>
      </div>
    </section>
  </main>
</template>
