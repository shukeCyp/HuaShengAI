<script setup>
import { onMounted, reactive, ref, watch } from 'vue'

import { callDesktop } from '../desktop'

const props = defineProps({
  desktopReady: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['status', 'database-path'])

const loading = ref(false)
const saving = ref(false)
const updatedAt = ref('')
const settings = reactive({
  headless: true,
  workerCount: 1,
  defaultMinPlayCount: 0,
  defaultMinDiggCount: 0,
  defaultMinForwardCount: 0
})

function updateStatus(message) {
  emit('status', message)
}

function updateDatabasePath(path) {
  if (path) {
    emit('database-path', path)
  }
}

function normalizeNonNegativeInt(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? fallback), 10)
  if (Number.isNaN(parsed) || parsed < 0) {
    throw new Error('请输入大于等于 0 的整数')
  }
  return parsed
}

function applyPayload(payload) {
  const next = payload.settings || {}
  settings.headless = Boolean(next.headless)
  settings.workerCount = Number(next.workerCount || 1)
  settings.defaultMinPlayCount = Number(next.defaultMinPlayCount || 0)
  settings.defaultMinDiggCount = Number(next.defaultMinDiggCount || 0)
  settings.defaultMinForwardCount = Number(next.defaultMinForwardCount || 0)
  updatedAt.value = String(payload.updatedAt || '')
  updateDatabasePath(payload.databasePath)
}

async function loadSettings(message = '微头条设置已载入') {
  if (!props.desktopReady) {
    return
  }

  loading.value = true
  try {
    const payload = await callDesktop('get_microheadline_settings')
    applyPayload(payload)
    updateStatus(message)
  } catch (error) {
    updateStatus(`加载微头条设置失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  if (!props.desktopReady) {
    updateStatus('当前不在 PyWebView 环境内')
    return
  }

  saving.value = true
  try {
    const payload = await callDesktop(
      'save_microheadline_settings',
      settings.headless,
      normalizeNonNegativeInt(settings.workerCount, 1),
      normalizeNonNegativeInt(settings.defaultMinPlayCount, 0),
      normalizeNonNegativeInt(settings.defaultMinDiggCount, 0),
      normalizeNonNegativeInt(settings.defaultMinForwardCount, 0)
    )
    applyPayload(payload)
    updateStatus('微头条设置已保存到数据库')
  } catch (error) {
    updateStatus(`保存微头条设置失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (props.desktopReady) {
    loadSettings()
  }
})

watch(
  () => props.desktopReady,
  (ready) => {
    if (ready) {
      loadSettings('微头条设置已载入')
    }
  }
)
</script>

<template>
  <article class="micro-settings">
    <div class="micro-settings__toolbar">
      <div>
        <strong>微头条设置</strong>
        <span>抓取自动化与默认门槛</span>
      </div>

      <div class="micro-settings__actions">
        <button
          type="button"
          class="toolbar-button secondary"
          :disabled="loading || !desktopReady"
          @click="loadSettings('微头条设置已刷新')"
        >
          {{ loading ? '刷新中...' : '从数据库刷新' }}
        </button>
        <button
          type="button"
          class="tts-primary-button settings-save-button"
          :disabled="saving || loading || !desktopReady"
          @click="saveSettings"
        >
          {{ saving ? '保存中...' : '保存微头条设置' }}
        </button>
      </div>
    </div>

    <section class="micro-settings__panel">
      <div class="settings-block-head">
        <strong>自动化执行</strong>
        <small>控制头条页面抓取时浏览器的运行方式</small>
      </div>

      <div class="micro-settings__form-grid">
        <label class="form-field">
          <span>是否无头</span>
          <select v-model="settings.headless">
            <option :value="true">是</option>
            <option :value="false">否</option>
          </select>
        </label>

        <label class="form-field">
          <span>浏览器执行线程数量</span>
          <input
            v-model.number="settings.workerCount"
            type="number"
            min="1"
            max="16"
          />
        </label>
      </div>
    </section>

    <section class="micro-settings__panel">
      <div class="settings-block-head">
        <strong>默认筛选门槛</strong>
        <small>文章抓取页会默认带入这三项数值，你也可以在抓取前临时修改</small>
      </div>

      <div class="micro-settings__form-grid micro-settings__form-grid--triple">
        <label class="form-field">
          <span>默认最低播放量</span>
          <input
            v-model.number="settings.defaultMinPlayCount"
            type="number"
            min="0"
          />
        </label>

        <label class="form-field">
          <span>默认最低点赞量</span>
          <input
            v-model.number="settings.defaultMinDiggCount"
            type="number"
            min="0"
          />
        </label>

        <label class="form-field">
          <span>默认最低转发量</span>
          <input
            v-model.number="settings.defaultMinForwardCount"
            type="number"
            min="0"
          />
        </label>
      </div>
    </section>
  </article>
</template>

<style scoped>
.micro-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.micro-settings__toolbar,
.micro-settings__panel {
  border-radius: 16px;
  border: 1px solid rgba(26, 26, 26, 0.08);
  background: #fff;
  box-shadow: 0 10px 30px rgba(23, 37, 84, 0.06);
}

.micro-settings__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
}

.micro-settings__toolbar strong {
  display: block;
  font-size: 18px;
  color: #172033;
}

.micro-settings__toolbar span {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  color: rgba(26, 26, 26, 0.66);
}

.micro-settings__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.micro-settings__panel {
  padding: 20px;
}

.micro-settings__form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.micro-settings__form-grid--triple {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

@media (max-width: 980px) {
  .micro-settings__toolbar,
  .micro-settings__form-grid,
  .micro-settings__form-grid--triple {
    grid-template-columns: 1fr;
  }

  .micro-settings__toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
