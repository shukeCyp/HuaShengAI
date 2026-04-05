<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { callDesktop } from '../desktop'

const props = defineProps({
  desktopReady: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['status', 'database-path'])

const accountsLoading = ref(false)
const running = ref(false)
const accountOptions = ref([])
const selectedAccountIds = ref([])
const result = ref(null)
const logs = ref([])
const filters = reactive({
  startTime: '',
  endTime: '',
  minPlayCount: '0',
  minDiggCount: '0',
  minForwardCount: '0'
})

const hasAccounts = computed(() => accountOptions.value.length > 0)
const hasSelection = computed(() => selectedAccountIds.value.length > 0)
const selectedCount = computed(() => selectedAccountIds.value.length)
const allSelected = computed(
  () => hasAccounts.value && selectedAccountIds.value.length === accountOptions.value.length
)
const summaryCards = computed(() => {
  if (!result.value) {
    return []
  }
  return [
    { label: '请求账号数', value: result.value.requestedCount },
    { label: '成功', value: result.value.succeededCount, tone: 'success' },
    { label: '告警', value: result.value.warningCount, tone: 'warning' },
    { label: '失败', value: result.value.failedCount, tone: 'danger' }
  ]
})

const timeRangePresets = [
  { key: 'yesterday', label: '昨天' },
  { key: 'lastThreeDays', label: '前三天' },
  { key: 'thisWeek', label: '本周' }
]

function formatLogTime(value = new Date()) {
  const hours = String(value.getHours()).padStart(2, '0')
  const minutes = String(value.getMinutes()).padStart(2, '0')
  const seconds = String(value.getSeconds()).padStart(2, '0')
  return `${hours}:${minutes}:${seconds}`
}

function appendLog(message) {
  const text = String(message || '').trim()
  if (!text) {
    return
  }
  logs.value = [
    {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      time: formatLogTime(),
      message: text
    },
    ...logs.value
  ].slice(0, 120)
}

function updateStatus(message) {
  appendLog(message)
  emit('status', message)
}

function updateDatabasePath(path) {
  if (path) {
    emit('database-path', path)
  }
}

function toggleAccount(accountId) {
  if (selectedAccountIds.value.includes(accountId)) {
    selectedAccountIds.value = selectedAccountIds.value.filter((item) => item !== accountId)
    return
  }
  selectedAccountIds.value = [...selectedAccountIds.value, accountId]
}

function toggleAllAccounts() {
  if (allSelected.value) {
    selectedAccountIds.value = []
    return
  }
  selectedAccountIds.value = accountOptions.value.map((item) => item.id)
}

function normalizeMetricValue(value) {
  const parsed = Number.parseInt(String(value || '').trim() || '0', 10)
  if (Number.isNaN(parsed) || parsed < 0) {
    throw new Error('筛选门槛必须是大于等于 0 的整数')
  }
  return parsed
}

function formatDateTime(value) {
  if (!value) {
    return '--'
  }
  return String(value).replace('T', ' ')
}

function getStatusText(status) {
  if (status === 'success') {
    return '成功'
  }
  if (status === 'warning') {
    return '告警'
  }
  return '失败'
}

function padNumber(value) {
  return String(value).padStart(2, '0')
}

function formatDateTimeLocalValue(value) {
  return [
    value.getFullYear(),
    padNumber(value.getMonth() + 1),
    padNumber(value.getDate())
  ].join('-') + `T${padNumber(value.getHours())}:${padNumber(value.getMinutes())}`
}

function cloneDate(value) {
  return new Date(value.getTime())
}

function startOfDay(value) {
  const next = cloneDate(value)
  next.setHours(0, 0, 0, 0)
  return next
}

function endOfDay(value) {
  const next = cloneDate(value)
  next.setHours(23, 59, 0, 0)
  return next
}

function applyDateRangePreset(presetKey) {
  const now = new Date()
  let start = null
  let end = null

  if (presetKey === 'yesterday') {
    const yesterday = cloneDate(now)
    yesterday.setDate(yesterday.getDate() - 1)
    start = startOfDay(yesterday)
    end = endOfDay(yesterday)
  }

  if (presetKey === 'lastThreeDays') {
    const threeDaysAgo = cloneDate(now)
    threeDaysAgo.setDate(threeDaysAgo.getDate() - 3)
    start = startOfDay(threeDaysAgo)
    end = now
  }

  if (presetKey === 'thisWeek') {
    const weekStart = cloneDate(now)
    const day = weekStart.getDay()
    const offset = day === 0 ? 6 : day - 1
    weekStart.setDate(weekStart.getDate() - offset)
    start = startOfDay(weekStart)
    end = now
  }

  if (!start || !end) {
    return
  }

  filters.startTime = formatDateTimeLocalValue(start)
  filters.endTime = formatDateTimeLocalValue(end)

  const presetLabel = timeRangePresets.find((item) => item.key === presetKey)?.label || '快捷时间'
  updateStatus(`已填入 ${presetLabel} 的抓取时间`)
}

async function loadSettingsDefaults() {
  if (!props.desktopReady) {
    return
  }
  try {
    const payload = await callDesktop('get_microheadline_settings')
    const settings = payload.settings || {}
    filters.minPlayCount = String(settings.defaultMinPlayCount ?? 0)
    filters.minDiggCount = String(settings.defaultMinDiggCount ?? 0)
    filters.minForwardCount = String(settings.defaultMinForwardCount ?? 0)
    updateDatabasePath(payload.databasePath)
  } catch (error) {
    updateStatus(`读取微头条默认设置失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

async function loadAccounts(message = '对标账号选项已加载') {
  if (!props.desktopReady) {
    accountOptions.value = []
    selectedAccountIds.value = []
    return
  }

  accountsLoading.value = true
  try {
    const options = await callDesktop('list_benchmark_account_options')
    accountOptions.value = options ?? []
    selectedAccountIds.value = selectedAccountIds.value.filter((id) =>
      accountOptions.value.some((item) => item.id === id)
    )
    updateStatus(`${message}，当前 ${accountOptions.value.length} 个账号`)
  } catch (error) {
    updateStatus(`加载对标账号选项失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    accountsLoading.value = false
  }
}

async function runMonitoring() {
  if (!props.desktopReady) {
    updateStatus('当前不在 PyWebView 环境内')
    return
  }
  if (!hasSelection.value) {
    updateStatus('请至少选择一个对标账号')
    return
  }
  if (filters.startTime && filters.endTime && filters.startTime > filters.endTime) {
    updateStatus('开始时间不能晚于结束时间')
    return
  }

  let minPlayCount = 0
  let minDiggCount = 0
  let minForwardCount = 0
  try {
    minPlayCount = normalizeMetricValue(filters.minPlayCount)
    minDiggCount = normalizeMetricValue(filters.minDiggCount)
    minForwardCount = normalizeMetricValue(filters.minForwardCount)
  } catch (error) {
    updateStatus(error instanceof Error ? error.message : String(error))
    return
  }

  running.value = true
  updateStatus(`开始批量抓取，目标账号 ${selectedAccountIds.value.length} 个`)
  try {
    const payload = await callDesktop('run_article_monitoring', {
      benchmarkAccountIds: [...selectedAccountIds.value],
      startTime: filters.startTime || null,
      endTime: filters.endTime || null,
      minPlayCount,
      minDiggCount,
      minForwardCount
    })
    result.value = payload
    for (const item of payload.results ?? []) {
      appendLog(
        `账号 #${item.benchmarkAccountId} ${getStatusText(item.status)}，保存 ${Number(item.savedCount || 0)} 条，原始 ${Number(item.articleCount || 0)} 条，筛选后 ${Number(item.filteredArticleCount || 0)} 条`
      )
      if (item.warning) {
        appendLog(`账号 #${item.benchmarkAccountId} 告警：${item.warning}`)
      }
      if (item.error) {
        appendLog(`账号 #${item.benchmarkAccountId} 错误：${item.error}`)
      }
    }
    updateStatus(
      `批量抓取完成，成功 ${payload.succeededCount} 个，告警 ${payload.warningCount} 个，失败 ${payload.failedCount} 个`
    )
  } catch (error) {
    updateStatus(`执行文章抓取失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  if (!props.desktopReady) {
    return
  }
  await loadSettingsDefaults()
  await loadAccounts()
})

watch(
  () => props.desktopReady,
  async (ready) => {
    if (!ready) {
      return
    }
    await loadSettingsDefaults()
    await loadAccounts('对标账号选项已载入')
  }
)
</script>

<template>
  <div class="monitor-page">
    <div class="monitor-toolbar">
      <button
        type="button"
        class="toolbar-button secondary"
        :disabled="accountsLoading || !desktopReady"
        @click="loadAccounts('对标账号选项已刷新')"
      >
        {{ accountsLoading ? '刷新中...' : '刷新账号' }}
      </button>
      <button
        type="button"
        class="toolbar-button primary"
        :disabled="running || !hasSelection || !desktopReady"
        @click="runMonitoring"
      >
        {{ running ? '抓取中...' : '执行抓取' }}
      </button>
    </div>

    <div class="monitor-layout">
      <section class="monitor-panel">
        <div class="monitor-panel__head">
          <div>
            <strong>账号选择</strong>
            <small>已选 {{ selectedCount }} / {{ accountOptions.length }}</small>
          </div>
          <button
            type="button"
            class="toolbar-button secondary"
            :disabled="!hasAccounts"
            @click="toggleAllAccounts"
          >
            {{ allSelected ? '清空选择' : '全选账号' }}
          </button>
        </div>

        <div v-if="hasAccounts" class="monitor-account-grid">
          <button
            v-for="account in accountOptions"
            :key="account.id"
            type="button"
            class="monitor-account"
            :data-selected="selectedAccountIds.includes(account.id)"
            @click="toggleAccount(account.id)"
          >
            <span class="monitor-account__check">
              {{ selectedAccountIds.includes(account.id) ? '✓' : '' }}
            </span>
            <span class="monitor-account__meta">
              <strong>账号 #{{ account.id }}</strong>
              <small>{{ account.url }}</small>
            </span>
          </button>
        </div>
        <div v-else class="empty-state monitor-empty">
          <p>还没有可抓取的账号</p>
          <span>先去“对标账号”页面添加至少一个头条账号链接。</span>
        </div>
      </section>

      <section class="monitor-panel">
        <div class="monitor-panel__head">
          <div>
            <strong>抓取条件</strong>
            <small>默认门槛来自“微头条设置”</small>
          </div>
        </div>

        <div class="monitor-preset-row">
          <button
            v-for="preset in timeRangePresets"
            :key="preset.key"
            type="button"
            class="monitor-preset-button"
            @click="applyDateRangePreset(preset.key)"
          >
            {{ preset.label }}
          </button>
        </div>

        <div class="monitor-form-grid">
          <label class="form-field">
            <span>开始时间</span>
            <input v-model="filters.startTime" type="datetime-local" />
          </label>
          <label class="form-field">
            <span>结束时间</span>
            <input v-model="filters.endTime" type="datetime-local" />
          </label>
          <label class="form-field">
            <span>最低播放量</span>
            <input v-model="filters.minPlayCount" type="number" min="0" />
          </label>
          <label class="form-field">
            <span>最低点赞量</span>
            <input v-model="filters.minDiggCount" type="number" min="0" />
          </label>
          <label class="form-field">
            <span>最低转发量</span>
            <input v-model="filters.minForwardCount" type="number" min="0" />
          </label>
        </div>
      </section>
    </div>

    <div v-if="summaryCards.length" class="monitor-summary">
      <article
        v-for="card in summaryCards"
        :key="card.label"
        class="monitor-summary__card"
        :data-tone="card.tone || 'normal'"
      >
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </article>
    </div>

    <section v-if="result" class="monitor-panel">
      <div class="monitor-panel__head">
        <div>
          <strong>本次抓取结果</strong>
          <small>每个账号都会分别返回抓取状态和命中数量</small>
        </div>
      </div>

      <div class="monitor-result-list">
        <article
          v-for="item in result.results"
          :key="`${item.benchmarkAccountId}-${item.monitorRunId || 0}`"
          class="monitor-result-card"
          :data-status="item.status"
        >
          <div class="monitor-result-card__head">
            <div>
              <strong>账号 #{{ item.benchmarkAccountId }}</strong>
              <small>{{ item.benchmarkAccountUrl }}</small>
            </div>
            <span class="monitor-result-card__badge">{{ getStatusText(item.status) }}</span>
          </div>

          <div class="monitor-result-card__metrics">
            <div>
              <span>保存</span>
              <strong>{{ item.savedCount }}</strong>
            </div>
            <div>
              <span>原始</span>
              <strong>{{ item.articleCount }}</strong>
            </div>
            <div>
              <span>筛选后</span>
              <strong>{{ item.filteredArticleCount }}</strong>
            </div>
            <div>
              <span>响应数</span>
              <strong>{{ item.captureCount }}</strong>
            </div>
          </div>

          <p v-if="item.warning" class="monitor-result-card__warning">{{ item.warning }}</p>
          <p v-if="item.error" class="monitor-result-card__error">{{ item.error }}</p>
        </article>
      </div>
    </section>

    <section class="monitor-panel">
      <div class="monitor-panel__head">
        <div>
          <strong>抓取日志</strong>
          <small>展示最近的抓取过程、告警和执行结果</small>
        </div>
      </div>

      <div v-if="logs.length" class="monitor-log-list">
        <article
          v-for="entry in logs"
          :key="entry.id"
          class="monitor-log-item"
        >
          <span class="monitor-log-item__time">{{ entry.time }}</span>
          <p class="monitor-log-item__message">{{ entry.message }}</p>
        </article>
      </div>
      <div v-else class="empty-state monitor-empty">
        <p>还没有抓取日志</p>
        <span>执行抓取或刷新账号后，这里会展示过程日志。</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.monitor-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.monitor-toolbar,
.monitor-panel,
.monitor-summary__card,
.monitor-result-card,
.monitor-log-item {
  border-radius: 16px;
  border: 1px solid rgba(26, 26, 26, 0.08);
  background: #fff;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.06);
}

.monitor-toolbar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  padding: 18px;
  background:
    radial-gradient(circle at top right, rgba(219, 234, 254, 0.9), transparent 34%),
    linear-gradient(135deg, #ffffff, #f8fbff 48%, #fffdf7);
}

.monitor-layout {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
}

.monitor-panel {
  padding: 18px;
}

.monitor-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.monitor-panel__head strong {
  display: block;
  font-size: 18px;
}

.monitor-panel__head small {
  color: rgba(26, 26, 26, 0.66);
  line-height: 1.6;
}

.monitor-account-grid,
.monitor-result-list,
.monitor-log-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.monitor-account {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(26, 26, 26, 0.08);
  background: linear-gradient(180deg, #fffef7, #ffffff);
  cursor: pointer;
  text-align: left;
  transition: all 0.18s ease;
}

.monitor-account[data-selected='true'] {
  border-color: rgba(37, 99, 235, 0.28);
  background: linear-gradient(180deg, rgba(219, 234, 254, 0.72), #ffffff);
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.08);
}

.monitor-account__check {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 1px solid rgba(37, 99, 235, 0.25);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #2563eb;
  flex-shrink: 0;
}

.monitor-account__meta {
  min-width: 0;
}

.monitor-account__meta strong,
.monitor-result-card__head strong {
  display: block;
  font-size: 15px;
  margin-bottom: 6px;
}

.monitor-account__meta small,
.monitor-result-card__head small {
  display: block;
  color: rgba(26, 26, 26, 0.66);
  line-height: 1.6;
  word-break: break-all;
}

.monitor-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.monitor-preset-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.monitor-preset-button {
  padding: 9px 14px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.95), #ffffff);
  color: #1d4ed8;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.monitor-preset-button:hover {
  border-color: rgba(37, 99, 235, 0.28);
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.08);
}

.monitor-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.monitor-summary__card {
  padding: 18px;
}

.monitor-summary__card span,
.monitor-result-card__metrics span {
  display: block;
  font-size: 12px;
  color: rgba(26, 26, 26, 0.5);
  margin-bottom: 6px;
}

.monitor-summary__card strong {
  display: block;
  font-size: 24px;
}

.monitor-summary__card[data-tone='success'] {
  background: linear-gradient(180deg, #f0fdf4, #ffffff);
}

.monitor-summary__card[data-tone='warning'] {
  background: linear-gradient(180deg, #fff7ed, #ffffff);
}

.monitor-summary__card[data-tone='danger'] {
  background: linear-gradient(180deg, #fff1f2, #ffffff);
}

.monitor-result-card {
  padding: 16px;
}

.monitor-result-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.monitor-result-card__badge {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
}

.monitor-result-card[data-status='warning'] .monitor-result-card__badge {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.monitor-result-card[data-status='failed'] .monitor-result-card__badge {
  background: rgba(244, 63, 94, 0.12);
  color: #be123c;
}

.monitor-result-card__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.monitor-result-card__metrics div {
  padding: 12px;
  border-radius: 12px;
  background: #fafaf9;
  border: 1px solid rgba(26, 26, 26, 0.06);
}

.monitor-result-card__metrics strong {
  display: block;
  font-size: 20px;
}

.monitor-result-card__warning,
.monitor-result-card__error {
  margin: 12px 0 0;
  line-height: 1.7;
}

.monitor-result-card__warning {
  color: #b45309;
}

.monitor-result-card__error {
  color: #be123c;
}

.monitor-log-item {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 12px;
  padding: 14px 16px;
}

.monitor-log-item__time {
  font-size: 12px;
  font-weight: 700;
  color: #2563eb;
}

.monitor-log-item__message {
  margin: 0;
  color: rgba(26, 26, 26, 0.78);
  line-height: 1.7;
  word-break: break-word;
}

.monitor-empty {
  padding: 26px 16px;
}

@media (max-width: 980px) {
  .monitor-layout,
  .monitor-summary,
  .monitor-form-grid,
  .monitor-result-card__metrics {
    grid-template-columns: 1fr;
  }

  .monitor-toolbar,
  .monitor-result-card__head {
    flex-direction: column;
  }

  .monitor-log-item {
    grid-template-columns: 1fr;
  }
}
</style>
