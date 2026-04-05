<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { callDesktop } from '../desktop'

const props = defineProps({
  desktopReady: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['status', 'database-path', 'tasks-created'])

const PAGE_SIZE = 20

const loading = ref(false)
const deleting = ref(false)
const bulkDialogOpen = ref(false)
const singleDialogOpen = ref(false)
const promptLoading = ref(false)
const bulkSubmitting = ref(false)
const singleSubmitting = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const totalPages = ref(1)
const promptOptions = ref([])
const selectedPromptIds = ref([])
const selectedSinglePromptId = ref(0)
const selectedArticle = ref(null)
const filters = reactive({
  keyword: ''
})

const hasItems = computed(() => items.value.length > 0)
const paginationSummary = computed(() => {
  if (!total.value) {
    return '暂无文章数据'
  }
  return `共 ${total.value} 条，第 ${page.value} / ${totalPages.value} 页`
})
const selectedPromptCount = computed(() => selectedPromptIds.value.length)
const queuedTaskCount = computed(() => total.value * selectedPromptCount.value)
const hasSelectedPrompts = computed(() => selectedPromptIds.value.length > 0)
const hasSelectedSinglePrompt = computed(() => Number(selectedSinglePromptId.value) > 0)
const selectedArticlePreview = computed(() => {
  return selectedArticle.value ? getArticlePreview(selectedArticle.value) : '未选择文章'
})

function updateStatus(message) {
  emit('status', message)
}

function updateDatabasePath(path) {
  if (path) {
    emit('database-path', path)
  }
}

function notifyTasksCreated(payload) {
  emit('tasks-created', payload)
}

function formatDateTime(value) {
  if (!value) {
    return '--'
  }
  return String(value).replace('T', ' ')
}

function formatMetric(value) {
  if (value === null || value === undefined || value === '') {
    return '--'
  }
  return value
}

function getArticlePreview(article) {
  const text = String(article.content || article.title || '').trim()
  if (!text) {
    return '未命名文章'
  }

  const chars = Array.from(text)
  if (chars.length <= 50) {
    return text
  }
  return `${chars.slice(0, 50).join('')}……`
}

function getUrlPreview(value) {
  const text = String(value || '').trim()
  if (text.length <= 48) {
    return text
  }
  return `${text.slice(0, 48)}...`
}

function getPromptPreview(value) {
  const text = String(value || '').trim()
  if (!text) {
    return '未填写提示词内容'
  }

  const chars = Array.from(text)
  if (chars.length <= 70) {
    return text
  }
  return `${chars.slice(0, 70).join('')}……`
}

function closeBulkDialog() {
  bulkDialogOpen.value = false
  selectedPromptIds.value = []
}

function closeSingleDialog() {
  singleDialogOpen.value = false
  singleSubmitting.value = false
  selectedSinglePromptId.value = 0
  selectedArticle.value = null
}

function togglePromptSelection(promptId) {
  const normalizedId = Number(promptId) || 0
  if (normalizedId <= 0) {
    return
  }

  if (selectedPromptIds.value.includes(normalizedId)) {
    selectedPromptIds.value = selectedPromptIds.value.filter((item) => item !== normalizedId)
    return
  }

  selectedPromptIds.value = [...selectedPromptIds.value, normalizedId]
}

function selectSinglePrompt(promptId) {
  const normalizedId = Number(promptId) || 0
  if (normalizedId <= 0) {
    return
  }
  selectedSinglePromptId.value = normalizedId
}

async function loadPromptOptions() {
  if (!props.desktopReady) {
    promptOptions.value = []
    return
  }

  promptLoading.value = true
  try {
    const payload = await callDesktop('get_model_settings')
    promptOptions.value = Array.isArray(payload?.prompts) ? payload.prompts : []
    updateDatabasePath(payload?.databasePath)
  } catch (error) {
    promptOptions.value = []
    updateStatus(`加载提示词失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    promptLoading.value = false
  }
}

async function openBulkDialog() {
  if (!props.desktopReady) {
    updateStatus('当前不在 PyWebView 环境内')
    return
  }
  if (!total.value) {
    updateStatus('当前没有可处理的文章')
    return
  }

  bulkDialogOpen.value = true
  selectedPromptIds.value = []
  await loadPromptOptions()
}

async function openSingleDialog(article) {
  if (!props.desktopReady) {
    updateStatus('当前不在 PyWebView 环境内')
    return
  }
  if (!article?.id) {
    updateStatus('当前文章数据无效，无法处理')
    return
  }

  selectedArticle.value = article
  selectedSinglePromptId.value = 0
  singleDialogOpen.value = true
  await loadPromptOptions()
}

async function submitBulkTasks() {
  if (!props.desktopReady) {
    updateStatus('当前不在 PyWebView 环境内')
    return
  }
  if (!hasSelectedPrompts.value) {
    updateStatus('请至少选择一个改写提示词')
    return
  }

  bulkSubmitting.value = true
  try {
    const payload = await callDesktop(
      'create_article_processing_tasks',
      {
        keyword: filters.keyword.trim()
      },
      selectedPromptIds.value
    )
    updateDatabasePath(payload?.databasePath)
    notifyTasksCreated(payload)
    closeBulkDialog()
    updateStatus(
      `已创建 ${Number(payload?.createdCount || 0)} 个任务，覆盖 ${Number(payload?.articleCount || 0)} 篇文章，使用账号 ID ${payload?.accountId || '--'}`
    )
  } catch (error) {
    updateStatus(`创建任务失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    bulkSubmitting.value = false
  }
}

async function submitSingleTask() {
  if (!props.desktopReady) {
    updateStatus('当前不在 PyWebView 环境内')
    return
  }
  if (!selectedArticle.value?.id) {
    updateStatus('当前没有可处理的文章')
    return
  }
  if (!hasSelectedSinglePrompt.value) {
    updateStatus('请先选择一个改写提示词')
    return
  }

  singleSubmitting.value = true
  try {
    const payload = await callDesktop(
      'create_single_article_processing_task',
      Number(selectedArticle.value.id),
      Number(selectedSinglePromptId.value)
    )
    updateDatabasePath(payload?.databasePath)
    notifyTasksCreated(payload)
    updateStatus(
      `已为文章 #${selectedArticle.value.id} 创建 ${Number(payload?.createdCount || 0)} 个任务，使用账号 ID ${payload?.accountId || '--'}`
    )
    closeSingleDialog()
  } catch (error) {
    updateStatus(`创建任务失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    singleSubmitting.value = false
  }
}

async function loadArticles(message = '文章列表已加载') {
  if (!props.desktopReady) {
    items.value = []
    total.value = 0
    totalPages.value = 1
    return
  }

  loading.value = true
  try {
    const payload = await callDesktop(
      'list_monitored_articles',
      {
        keyword: filters.keyword.trim()
      },
      page.value,
      PAGE_SIZE
    )
    items.value = payload.items ?? []
    total.value = Number(payload.total || 0)
    totalPages.value = Math.max(1, Number(payload.totalPages || 1))
    updateDatabasePath(payload.databasePath)
    updateStatus(`${message}，当前共 ${total.value} 条`)
  } catch (error) {
    updateStatus(`加载文章列表失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    loading.value = false
  }
}

async function searchArticles() {
  page.value = 1
  await loadArticles('文章列表已筛选')
}

async function changePage(nextPage) {
  if (loading.value || nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) {
    return
  }
  page.value = nextPage
  await loadArticles('文章列表已翻页')
}

async function deleteAllArticles() {
  if (!props.desktopReady) {
    updateStatus('当前不在 PyWebView 环境内')
    return
  }
  if (!total.value) {
    updateStatus('当前没有可删除的文章')
    return
  }
  if (!window.confirm(`确认删除所有文章？\n\n当前文章库共有 ${total.value} 条记录，删除后不可恢复。`)) {
    return
  }

  deleting.value = true
  try {
    const payload = await callDesktop('delete_all_monitored_articles')
    updateDatabasePath(payload.databasePath)
    page.value = 1
    await loadArticles('文章列表已清空')
    updateStatus(`已删除 ${Number(payload.deletedCount || 0)} 条文章`)
  } catch (error) {
    updateStatus(`删除文章失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  if (props.desktopReady) {
    loadArticles()
  }
})

watch(
  () => props.desktopReady,
  (ready) => {
    if (ready) {
      page.value = 1
      loadArticles('文章列表已载入')
    }
  }
)
</script>

<template>
  <div class="article-library-page">
    <div class="list-toolbar article-library-toolbar">
      <div class="tasks-toolbar-copy">
        <strong>文章列表</strong>
        <span>展示文章库中已经入库的微头条文章。</span>
      </div>

      <div class="article-library-toolbar__actions">
        <label class="search-field article-library-search">
          <input
            v-model="filters.keyword"
            type="text"
            placeholder="搜索标题或正文关键词"
            @keydown.enter.prevent="searchArticles"
          />
        </label>
        <button
          type="button"
          class="toolbar-button secondary"
          :disabled="loading || deleting || !desktopReady"
          @click="searchArticles"
        >
          搜索
        </button>
        <button
          type="button"
          class="toolbar-button secondary"
          :disabled="loading || deleting || !desktopReady"
          @click="loadArticles('文章列表已刷新')"
        >
          {{ loading ? '刷新中...' : '刷新列表' }}
        </button>
        <button
          type="button"
          class="toolbar-button primary"
          :disabled="loading || deleting || !desktopReady || !total"
          @click="openBulkDialog"
        >
          全量处理
        </button>
        <button
          type="button"
          class="toolbar-button article-library-delete-button"
          :disabled="loading || deleting || !desktopReady || !total"
          @click="deleteAllArticles"
        >
          {{ deleting ? '删除中...' : '删除所有文章' }}
        </button>
      </div>
    </div>

    <div class="article-library-list">
      <article
          v-for="article in items"
          :key="article.id"
          class="article-library-card"
        >
        <div class="article-library-card__head">
          <div class="article-library-card__copy">
            <strong>{{ getArticlePreview(article) }}</strong>
            <small>
              账号 #{{ article.benchmarkAccountId }} · {{ getUrlPreview(article.benchmarkAccountUrl) }}
            </small>
          </div>
          <span class="article-library-card__time">{{ formatDateTime(article.publishTime) }}</span>
        </div>

        <div class="article-library-card__metrics">
          <span>播放 {{ formatMetric(article.playCount) }}</span>
          <span>点赞 {{ formatMetric(article.diggCount) }}</span>
        </div>

        <div class="article-library-card__actions">
          <button
            type="button"
            class="toolbar-button secondary"
            :disabled="promptLoading || singleSubmitting || !desktopReady"
            @click="openSingleDialog(article)"
          >
            处理
          </button>
        </div>
      </article>

      <div v-if="!hasItems" class="empty-state article-library-empty">
        <p>还没有文章数据</p>
        <span>先去“文章抓取”执行一次抓取，文章入库后会显示在这里。</span>
      </div>
    </div>

    <div class="article-library-pagination">
      <span>{{ paginationSummary }}</span>
      <div class="panel-actions">
        <button
          type="button"
          class="toolbar-button secondary"
          :disabled="loading || page <= 1"
          @click="changePage(page - 1)"
        >
          上一页
        </button>
        <button
          type="button"
          class="toolbar-button secondary"
          :disabled="loading || page >= totalPages"
          @click="changePage(page + 1)"
        >
          下一页
        </button>
      </div>
    </div>

    <div
      v-if="bulkDialogOpen"
      class="dialog-backdrop"
      @click.self="closeBulkDialog"
    >
      <section
        class="article-bulk-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="article-bulk-dialog-title"
      >
        <div class="article-bulk-dialog__head">
          <div>
            <p class="panel-kicker">文章处理</p>
            <h3 id="article-bulk-dialog-title">全量处理</h3>
            <p class="article-bulk-dialog__description">
              当前将处理 {{ total }} 篇文章。至少选择一个提示词，可多选；每篇文章会按每个提示词各创建一个任务。
            </p>
          </div>
          <button
            type="button"
            class="toolbar-button secondary"
            @click="closeBulkDialog"
          >
            取消
          </button>
        </div>

        <div class="article-bulk-summary">
          <div class="article-bulk-summary__card">
            <span>文章数量</span>
            <strong>{{ total }}</strong>
            <small>{{ filters.keyword ? `关键词：${filters.keyword}` : '当前为全部文章' }}</small>
          </div>
          <div class="article-bulk-summary__card">
            <span>提示词数量</span>
            <strong>{{ selectedPromptCount }}</strong>
            <small>{{ hasSelectedPrompts ? '可以多选' : '至少选择一个提示词' }}</small>
          </div>
          <div class="article-bulk-summary__card">
            <span>预计任务数</span>
            <strong>{{ queuedTaskCount }}</strong>
            <small>计算方式：文章数 × 提示词数</small>
          </div>
        </div>

        <section class="article-bulk-dialog__section">
          <div class="settings-block-head">
            <strong>改写提示词</strong>
            <small>点击卡片进行多选</small>
          </div>

          <div v-if="promptOptions.length" class="article-bulk-prompt-grid">
            <button
              v-for="prompt in promptOptions"
              :key="prompt.id"
              type="button"
              class="article-bulk-prompt-card"
              :data-active="selectedPromptIds.includes(prompt.id)"
              @click="togglePromptSelection(prompt.id)"
            >
              <div class="article-bulk-prompt-card__head">
                <strong>提示词 #{{ prompt.id }}</strong>
                <span>{{ selectedPromptIds.includes(prompt.id) ? '已选择' : '点击选择' }}</span>
              </div>
              <p>{{ getPromptPreview(prompt.content) }}</p>
            </button>
          </div>

          <div v-else class="tts-empty-state">
            {{ promptLoading ? '正在加载提示词...' : '当前还没有已保存的改写提示词，请先到设置页添加。' }}
          </div>
        </section>

        <div class="article-bulk-dialog__actions">
          <button
            type="button"
            class="toolbar-button secondary"
            :disabled="promptLoading || bulkSubmitting"
            @click="loadPromptOptions"
          >
            {{ promptLoading ? '加载中...' : '刷新提示词' }}
          </button>
          <button
            type="button"
            class="toolbar-button primary"
            :disabled="promptLoading || bulkSubmitting || !hasSelectedPrompts"
            @click="submitBulkTasks"
          >
            {{ bulkSubmitting ? '创建中...' : `确定创建 ${queuedTaskCount} 个任务` }}
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="singleDialogOpen"
      class="dialog-backdrop"
      @click.self="closeSingleDialog"
    >
      <section
        class="article-bulk-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="article-single-dialog-title"
      >
        <div class="article-bulk-dialog__head">
          <div>
            <p class="panel-kicker">文章处理</p>
            <h3 id="article-single-dialog-title">处理文章</h3>
            <p class="article-bulk-dialog__description">
              当前会为这篇文章创建 1 个任务。请选择 1 个改写提示词。
            </p>
          </div>
          <button
            type="button"
            class="toolbar-button secondary"
            @click="closeSingleDialog"
          >
            取消
          </button>
        </div>

        <div class="article-bulk-summary">
          <div class="article-bulk-summary__card">
            <span>文章 ID</span>
            <strong>{{ selectedArticle?.id || '--' }}</strong>
            <small>当前只会创建 1 个任务</small>
          </div>
          <div class="article-bulk-summary__card">
            <span>文章预览</span>
            <strong>{{ selectedArticlePreview }}</strong>
            <small>{{ selectedArticle ? formatDateTime(selectedArticle.publishTime) : '--' }}</small>
          </div>
          <div class="article-bulk-summary__card">
            <span>提示词状态</span>
            <strong>{{ hasSelectedSinglePrompt ? '已选择' : '未选择' }}</strong>
            <small>{{ hasSelectedSinglePrompt ? '点击下方按钮即可创建任务' : '请先选择一个提示词' }}</small>
          </div>
        </div>

        <section class="article-bulk-dialog__section">
          <div class="settings-block-head">
            <strong>改写提示词</strong>
            <small>点击卡片单选</small>
          </div>

          <div v-if="promptOptions.length" class="article-bulk-prompt-grid">
            <button
              v-for="prompt in promptOptions"
              :key="prompt.id"
              type="button"
              class="article-bulk-prompt-card"
              :data-active="selectedSinglePromptId === prompt.id"
              @click="selectSinglePrompt(prompt.id)"
            >
              <div class="article-bulk-prompt-card__head">
                <strong>提示词 #{{ prompt.id }}</strong>
                <span>{{ selectedSinglePromptId === prompt.id ? '已选择' : '点击选择' }}</span>
              </div>
              <p>{{ getPromptPreview(prompt.content) }}</p>
            </button>
          </div>

          <div v-else class="tts-empty-state">
            {{ promptLoading ? '正在加载提示词...' : '当前还没有已保存的改写提示词，请先到设置页添加。' }}
          </div>
        </section>

        <div class="article-bulk-dialog__actions">
          <button
            type="button"
            class="toolbar-button secondary"
            :disabled="promptLoading || singleSubmitting"
            @click="loadPromptOptions"
          >
            {{ promptLoading ? '加载中...' : '刷新提示词' }}
          </button>
          <button
            type="button"
            class="toolbar-button primary"
            :disabled="promptLoading || singleSubmitting || !hasSelectedSinglePrompt"
            @click="submitSingleTask"
          >
            {{ singleSubmitting ? '创建中...' : '确定创建 1 个任务' }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.article-library-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.article-library-toolbar {
  align-items: center;
}

.article-library-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.article-library-search {
  min-width: 320px;
}

.article-library-delete-button {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.08);
  color: #b42318;
}

.article-library-delete-button:hover:not(:disabled) {
  border-color: rgba(239, 68, 68, 0.36);
  background: rgba(239, 68, 68, 0.14);
}

.article-library-card__actions {
  display: flex;
  justify-content: flex-end;
}

.article-bulk-dialog {
  width: min(920px, 100%);
  max-height: 90vh;
  padding: 24px;
  border-radius: 20px;
  background: linear-gradient(180deg, #ffffff, #fffdf8);
  border: 1px solid rgba(26, 26, 26, 0.08);
  box-shadow: 0 24px 60px rgba(17, 24, 39, 0.14);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.article-bulk-dialog__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.article-bulk-dialog__head h3 {
  margin: 0;
  font-size: 28px;
  color: #172033;
}

.article-bulk-dialog__description {
  margin: 10px 0 0;
  color: rgba(26, 26, 26, 0.62);
  line-height: 1.7;
}

.article-bulk-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.article-bulk-summary__card {
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid rgba(26, 26, 26, 0.08);
  background: #f8fbfa;
}

.article-bulk-summary__card span {
  display: block;
  font-size: 11px;
  color: rgba(26, 26, 26, 0.5);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.article-bulk-summary__card strong {
  display: block;
  margin-top: 8px;
  font-size: 28px;
  color: #172033;
}

.article-bulk-summary__card small {
  display: block;
  margin-top: 8px;
  color: rgba(26, 26, 26, 0.58);
  line-height: 1.6;
}

.article-bulk-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.article-bulk-prompt-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.article-bulk-prompt-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(26, 26, 26, 0.08);
  background: #ffffff;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease;
  box-shadow: 0 8px 24px rgba(17, 24, 39, 0.05);
}

.article-bulk-prompt-card:hover {
  border-color: rgba(25, 227, 162, 0.45);
  transform: translateY(-1px);
}

.article-bulk-prompt-card[data-active='true'] {
  border-color: #19e3a2;
  background: #f3fffa;
  box-shadow: inset 0 0 0 1px rgba(25, 227, 162, 0.18);
}

.article-bulk-prompt-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}

.article-bulk-prompt-card__head strong {
  font-size: 16px;
  color: #172033;
}

.article-bulk-prompt-card__head span {
  font-size: 12px;
  color: rgba(26, 26, 26, 0.5);
}

.article-bulk-prompt-card p {
  margin: 0;
  color: rgba(26, 26, 26, 0.68);
  line-height: 1.7;
}

.article-bulk-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.article-library-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.article-library-card {
  border-radius: 16px;
  border: 1px solid rgba(26, 26, 26, 0.08);
  background: #fff;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.05);
  padding: 18px 20px;
}

.article-library-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.article-library-card__copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.article-library-card__copy strong {
  font-size: 16px;
  line-height: 1.6;
  color: #172033;
  word-break: break-word;
}

.article-library-card__copy small {
  color: rgba(26, 26, 26, 0.6);
  line-height: 1.5;
}

.article-library-card__time {
  flex-shrink: 0;
  color: rgba(26, 26, 26, 0.62);
  font-size: 13px;
}

.article-library-card__metrics {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.article-library-card__metrics span {
  display: inline-flex;
  align-items: center;
  padding: 7px 12px;
  border-radius: 999px;
  background: #f4f7fb;
  color: #38506c;
  font-size: 13px;
  font-weight: 600;
}

.article-library-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 2px;
  color: rgba(26, 26, 26, 0.68);
  font-size: 14px;
}

@media (max-width: 900px) {
  .article-library-toolbar,
  .article-library-card__head,
  .article-library-pagination {
    flex-direction: column;
    align-items: stretch;
  }

  .article-library-search {
    min-width: 0;
  }

  .article-bulk-summary,
  .article-bulk-prompt-grid {
    grid-template-columns: 1fr;
  }
}
</style>
