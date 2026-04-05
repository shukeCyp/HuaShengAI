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

const PAGE_SIZE = 200

const loading = ref(false)
const submitting = ref(false)
const actingId = ref(null)
const items = ref([])
const total = ref(0)
const dialogOpen = ref(false)
const dialogMode = ref('single')
const batchUrls = ref('')
const form = reactive({
  id: null,
  url: ''
})

const isEditing = computed(() => form.id !== null)
const isBatchMode = computed(() => dialogMode.value === 'batch' && !isEditing.value)
const lastActionLabel = computed(() => {
  if (loading.value) {
    return '加载中'
  }
  if (submitting.value) {
    return isEditing.value ? '更新中' : '新增中'
  }
  if (actingId.value !== null) {
    return '处理中'
  }
  return '空闲'
})

function updateStatus(message) {
  emit('status', message)
}

function updateDatabasePath(path) {
  if (path) {
    emit('database-path', path)
  }
}

function resetForm() {
  form.id = null
  form.url = ''
  batchUrls.value = ''
  dialogMode.value = 'single'
}

function openCreateDialog() {
  resetForm()
  dialogOpen.value = true
  updateStatus('准备新增对标账号')
}

function openEditDialog(item) {
  form.id = item.id
  form.url = item.url
  batchUrls.value = ''
  dialogMode.value = 'single'
  dialogOpen.value = true
  updateStatus(`准备编辑对标账号 ${item.id}`)
}

function closeDialog() {
  if (submitting.value) {
    return
  }
  dialogOpen.value = false
  resetForm()
}

function isValidUrl(value) {
  try {
    const url = new URL(String(value || '').trim())
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

function formatDateTime(value) {
  if (!value) {
    return '--'
  }
  return String(value).replace('T', ' ')
}

function getUrlPreview(value) {
  const text = String(value || '').trim()
  if (text.length <= 84) {
    return text
  }
  return `${text.slice(0, 84)}...`
}

async function loadAccounts(message = '对标账号列表已加载') {
  if (!props.desktopReady) {
    items.value = []
    total.value = 0
    return
  }

  loading.value = true
  try {
    const payload = await callDesktop('list_benchmark_accounts', 1, PAGE_SIZE)
    items.value = payload.items ?? []
    total.value = Number(payload.total || 0)
    updateDatabasePath(payload.databasePath)
    updateStatus(`${message}，当前 ${total.value} 个账号`)
  } catch (error) {
    updateStatus(`加载对标账号失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    loading.value = false
  }
}

async function submitDialog() {
  if (isBatchMode.value) {
    const urls = batchUrls.value
      .split(/\r?\n/)
      .map((item) => String(item || '').trim())
      .filter(Boolean)

    if (!urls.length) {
      updateStatus('请至少输入一个账号链接')
      return
    }

    const invalidUrl = urls.find((item) => !isValidUrl(item))
    if (invalidUrl) {
      updateStatus(`链接格式不正确: ${invalidUrl}`)
      return
    }

    submitting.value = true
    try {
      let successCount = 0
      let failedCount = 0

      for (const url of urls) {
        try {
          await callDesktop('create_benchmark_account', url)
          successCount += 1
        } catch {
          failedCount += 1
        }
      }

      dialogOpen.value = false
      resetForm()
      await loadAccounts('对标账号列表已刷新')
      if (failedCount > 0) {
        updateStatus(`批量添加完成，成功 ${successCount} 条，失败 ${failedCount} 条`)
        return
      }
      updateStatus(`批量添加完成，共 ${successCount} 条`)
    } catch (error) {
      updateStatus(`批量添加失败: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      submitting.value = false
    }
    return
  }

  const normalizedUrl = String(form.url || '').trim()
  if (!normalizedUrl) {
    updateStatus('请输入对标账号链接')
    return
  }
  if (!isValidUrl(normalizedUrl)) {
    updateStatus('请输入有效的 http/https 链接')
    return
  }

  submitting.value = true
  try {
    if (isEditing.value) {
      await callDesktop('update_benchmark_account', form.id, normalizedUrl)
      updateStatus('对标账号已更新')
    } else {
      await callDesktop('create_benchmark_account', normalizedUrl)
      updateStatus('对标账号已新增')
    }
    dialogOpen.value = false
    resetForm()
    await loadAccounts('对标账号列表已刷新')
  } catch (error) {
    updateStatus(`保存对标账号失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    submitting.value = false
  }
}

async function deleteAccount(item) {
  if (!window.confirm(`确认删除该对标账号？\n\n${item.url}`)) {
    return
  }

  actingId.value = item.id
  try {
    const success = await callDesktop('delete_benchmark_account', item.id)
    if (!success) {
      throw new Error('删除失败')
    }
    updateStatus('对标账号已删除')
    await loadAccounts('对标账号列表已刷新')
  } catch (error) {
    updateStatus(`删除对标账号失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    actingId.value = null
  }
}

async function quickMonitor(item) {
  actingId.value = item.id
  try {
    const result = await callDesktop('run_account_monitor', {
      url: item.url,
      benchmarkAccountId: item.id,
      singleCapture: true
    })
    await loadAccounts('对标账号列表已刷新')
    updateStatus(
      `单账号抓取完成，保存 ${Number(result.savedCount || 0)} 条，筛选后 ${Number(result.filteredArticleCount || 0)} 条`
    )
  } catch (error) {
    updateStatus(`执行单账号抓取失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    actingId.value = null
  }
}

onMounted(() => {
  if (props.desktopReady) {
    loadAccounts()
  }
})

watch(
  () => props.desktopReady,
  (ready) => {
    if (ready) {
      loadAccounts('对标账号列表已载入')
    }
  }
)
</script>

<template>
  <div class="benchmark-page">
    <div class="benchmark-toolbar">
      <div class="benchmark-toolbar__meta">
        <span>共 {{ total }} 个账号</span>
        <small>支持单个添加、批量添加、编辑、删除和快速抓取</small>
      </div>
      <div class="benchmark-toolbar__actions">
        <button
          type="button"
          class="toolbar-button secondary"
          :disabled="loading || !desktopReady"
          @click="loadAccounts('对标账号列表已刷新')"
        >
          {{ loading ? '刷新中...' : '刷新' }}
        </button>
        <button
          type="button"
          class="toolbar-button primary"
          :disabled="!desktopReady"
          @click="openCreateDialog"
        >
          添加对标账号
        </button>
      </div>
    </div>

    <div v-if="items.length" class="benchmark-list">
      <article
        v-for="item in items"
        :key="item.id"
        class="benchmark-row"
      >
        <div class="benchmark-row__main">
          <div>
            <p class="benchmark-row__title">账号 #{{ item.id }}</p>
            <a
              class="benchmark-row__url"
              :href="item.url"
              target="_blank"
              rel="noreferrer"
              :title="item.url"
            >
              {{ getUrlPreview(item.url) }}
            </a>
          </div>
        </div>

        <div class="benchmark-row__actions">
          <button
            type="button"
            class="toolbar-button secondary"
            :disabled="actingId === item.id"
            @click="window.open(item.url, '_blank', 'noopener,noreferrer')"
          >
            打开
          </button>
          <button
            type="button"
            class="toolbar-button primary benchmark-delete-button"
            :disabled="actingId === item.id"
            @click="deleteAccount(item)"
          >
            删除
          </button>
        </div>
      </article>
    </div>

    <div v-else class="empty-state benchmark-empty">
      <p>还没有对标账号</p>
      <span>先添加一个头条账号链接，再去“文章抓取”页面批量执行。</span>
    </div>

    <div
      v-if="dialogOpen"
      class="dialog-backdrop"
      @click.self="closeDialog"
    >
      <section class="benchmark-dialog">
        <div class="benchmark-dialog__head">
          <div>
            <h3>{{ isEditing ? '编辑对标账号' : '添加对标账号' }}</h3>
            <p class="benchmark-dialog__text">
              {{ isEditing ? '仅支持修改单个账号链接。' : '支持单个添加，也支持批量添加，一行一个账号链接。' }}
            </p>
          </div>
        </div>

        <div v-if="!isEditing" class="benchmark-mode-tabs">
          <button
            type="button"
            class="benchmark-mode-tab"
            :data-active="dialogMode === 'single'"
            @click="dialogMode = 'single'"
          >
            单个添加
          </button>
          <button
            type="button"
            class="benchmark-mode-tab"
            :data-active="dialogMode === 'batch'"
            @click="dialogMode = 'batch'"
          >
            批量添加
          </button>
        </div>

        <label v-if="!isBatchMode" class="form-field">
          <span>账号链接</span>
          <input
            v-model="form.url"
            type="text"
            placeholder="https://www.toutiao.com/c/user/token/..."
          />
        </label>

        <label v-else class="form-field">
          <span>批量账号链接</span>
          <textarea
            v-model="batchUrls"
            rows="10"
            placeholder="一行一个账号链接"
          />
        </label>

        <div class="benchmark-dialog__actions">
          <button
            type="button"
            class="toolbar-button secondary"
            :disabled="submitting"
            @click="closeDialog"
          >
            取消
          </button>
          <button
            type="button"
            class="toolbar-button primary"
            :disabled="submitting"
            @click="submitDialog"
          >
            {{
              submitting
                ? '保存中...'
                : isEditing
                  ? '保存修改'
                  : isBatchMode
                    ? '开始批量添加'
                    : '新增账号'
            }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.benchmark-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.benchmark-toolbar,
.benchmark-row,
.benchmark-dialog {
  border-radius: 14px;
  border: 1px solid rgba(26, 26, 26, 0.08);
  background: #fff;
  box-shadow: 0 10px 30px rgba(23, 37, 84, 0.06);
}

.benchmark-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
}

.benchmark-toolbar__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.benchmark-toolbar__meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.benchmark-toolbar__meta span {
  font-size: 14px;
  font-weight: 600;
}

.benchmark-toolbar__meta small {
  color: rgba(26, 26, 26, 0.62);
}

.benchmark-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.benchmark-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
}

.benchmark-row__main {
  min-width: 0;
  flex: 1;
}

.benchmark-row__title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
}

.benchmark-row__url {
  color: #2b5ac6;
  line-height: 1.6;
  text-decoration: none;
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.benchmark-row__url:hover {
  text-decoration: underline;
}

.benchmark-row__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
  flex-shrink: 0;
}

.benchmark-delete-button {
  background: linear-gradient(135deg, #fb7185, #ef4444);
  border-color: #ef4444;
}

.benchmark-empty {
  padding: 36px 20px;
}

.benchmark-dialog {
  width: min(560px, calc(100vw - 32px));
  padding: 22px;
}

.benchmark-dialog__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.benchmark-dialog__head h3 {
  margin: 0 0 6px;
  font-size: 22px;
}

.benchmark-dialog__text {
  margin: 0;
  color: rgba(26, 26, 26, 0.64);
  line-height: 1.6;
}

.benchmark-mode-tabs {
  display: inline-flex;
  gap: 6px;
  padding: 4px;
  border-radius: 12px;
  background: #f5f5f5;
  margin-bottom: 16px;
}

.benchmark-mode-tab {
  padding: 9px 14px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: rgba(26, 26, 26, 0.68);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.benchmark-mode-tab[data-active='true'] {
  background: #fff;
  color: #1a1a1a;
  box-shadow: 0 4px 16px rgba(23, 37, 84, 0.08);
}

.benchmark-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

@media (max-width: 980px) {
  .benchmark-toolbar,
  .benchmark-row__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .benchmark-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
