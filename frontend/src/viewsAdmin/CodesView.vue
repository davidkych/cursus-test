<!-- frontend/src/viewsAdmin/CodesView.vue -->
<script setup>
import { onMounted, reactive, ref, computed } from 'vue'
import {
  mdiKeyVariant,
  mdiContentCopy,
  mdiDownload,
  mdiTable,
  mdiAlertCircle,
} from '@mdi/js'

import LayoutAuthenticated from '@/layouts/LayoutAuthenticated.vue'
import SectionMain from '@/components/SectionMain.vue'
import SectionTitleLineWithButton from '@/components/SectionTitleLineWithButton.vue'
import CardBox from '@/components/CardBox.vue'
import FormField from '@/components/FormField.vue'
import FormControl from '@/components/FormControl.vue'
import BaseButton from '@/components/BaseButton.vue'
import BaseButtons from '@/components/BaseButtons.vue'

import {
  listFunctions,
  generateOneOff,
  generateReusable,
  generateSingle,
} from '@/services/codes.js'

/* ─────────────────────────── state ─────────────────────────── */
const functions = ref([])
const loadingFunctions = ref(false)
const errorFunctions = ref('')

const form = reactive({
  type: 'oneoff',     // 'oneoff' | 'reusable' | 'single'
  functionKey: '',
  expiresLocal: '',   // value from <input type="datetime-local">
  count: 10,          // only for oneoff
  code: '',           // only for reusable/single
})

const submitting = ref(false)
const submitError = ref('')

/** Generated rows normalized for the table */
const rows = ref([])

const hasRows = computed(() => rows.value.length > 0)
const selectedFunction = computed(() =>
  functions.value.find(f => f.key === form.functionKey) || null,
)

/* Resolve current type id regardless of how the select binds (string or object) */
const selectedTypeId = computed(() =>
  typeof form.type === 'string' ? form.type : (form.type && form.type.id) || ''
)

/* ─────────────────────── lifecycle/loaders ─────────────────────── */
onMounted(async () => {
  await loadFunctions()
})

async function loadFunctions() {
  loadingFunctions.value = true
  errorFunctions.value = ''
  try {
    const items = await listFunctions()
    functions.value = Array.isArray(items) ? items : []
  } catch (err) {
    errorFunctions.value = err?.message || 'Failed to load functions'
  } finally {
    loadingFunctions.value = false
  }
}

/* ───────────────────────── helpers ───────────────────────── */
/**
 * Parse various local date strings into a Date and return ISO UTC with seconds (no ms).
 * - Primary path: native datetime-local value "YYYY-MM-DDTHH:mm"
 * - Fallback: locale strings like "22 / 08 / 2025, 02:02 am"
 */
function toUtcIso(localValue) {
  if (!localValue) return ''

  let d = null

  // 1) Native datetime-local (YYYY-MM-DDTHH:mm[..])
  // Browsers treat this as local time when passed to new Date(...)
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(\:\d{2})?$/.test(localValue)) {
    d = new Date(localValue)
  }

  // 2) Fallback: "DD / MM / YYYY, HH:mm am|pm"
  if (!d || isNaN(d.getTime())) {
    const m = localValue
      .trim()
      .match(/^(\d{1,2})\s*\/\s*(\d{1,2})\s*\/\s*(\d{4})\s*,\s*(\d{1,2}):(\d{2})\s*(am|pm)$/i)
    if (m) {
      let [, dd, mm, yyyy, hh, min, ap] = m
      dd = Number(dd)
      mm = Number(mm)
      let H = Number(hh) % 12
      if (/pm/i.test(ap)) H += 12
      d = new Date(Number(yyyy), mm - 1, dd, H, Number(min), 0)
    }
  }

  // 3) Last attempt: let the engine try
  if (!d || isNaN(d.getTime())) d = new Date(localValue)

  if (isNaN(d.getTime())) return ''

  // Return ISO with seconds, no milliseconds
  const iso = d.toISOString().replace(/\.\d{3}Z$/, 'Z')
  return iso
}

function ensureFuture(iso) {
  try {
    const t = new Date(iso).getTime()
    return t > Date.now()
  } catch {
    return false
  }
}

/* Build CSV with header order: code,type,function,expires_at,created_at */
function toCsv(data) {
  const header = ['code', 'type', 'function', 'expires_at', 'created_at']
  const esc = (v) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [header.join(',')]
  for (const r of data) {
    lines.push([esc(r.code), esc(r.type), esc(r.function), esc(r.expires_at), esc(r.created_at)].join(','))
  }
  return lines.join('\n')
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function downloadCsv(filename, csvText) {
  const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/* ───────────────────────── actions ───────────────────────── */
async function onSubmit() {
  submitError.value = ''
  if (!form.functionKey) {
    submitError.value = 'Please select a function'
    return
  }

  const iso = toUtcIso(form.expiresLocal)
  if (!iso) {
    submitError.value = 'Please select a valid expiry date & time'
    return
  }
  if (!ensureFuture(iso)) {
    submitError.value = 'Expiry must be in the future'
    return
  }

  const typeId = selectedTypeId.value

  if (typeId === 'oneoff') {
    if (!form.count || Number(form.count) < 1) {
      submitError.value = 'Count must be at least 1'
      return
    }
  } else {
    if (!form.code || !form.code.trim()) {
      submitError.value = 'Please enter a code'
      return
    }
  }

  submitting.value = true
  try {
    let result
    if (typeId === 'oneoff') {
      result = await generateOneOff({
        function: form.functionKey,
        expires_at: iso,
        count: Number(form.count),
      })
      const items = Array.isArray(result?.codes) ? result.codes : []
      const mapped = items.map(it => ({
        code: it.code,
        type: it.type,
        function: it.function,
        expires_at: it.expires_at,
        created_at: it.created_at,
      }))
      rows.value = mapped.concat(rows.value)
    } else if (typeId === 'reusable') {
      result = await generateReusable({
        code: form.code.trim(),
        function: form.functionKey,
        expires_at: iso,
      })
      const row = {
        code: result.code,
        type: result.type,
        function: result.function,
        expires_at: result.expires_at,
        created_at: result.created_at,
      }
      rows.value = [row, ...rows.value]
    } else if (typeId === 'single') {
      result = await generateSingle({
        code: form.code.trim(),
        function: form.functionKey,
        expires_at: iso,
      })
      const row = {
        code: result.code,
        type: result.type,
        function: result.function,
        expires_at: result.expires_at,
        created_at: result.created_at,
      }
      rows.value = [row, ...rows.value]
    }
  } catch (err) {
    // Surface FastAPI error details coming from services/codes.js
    submitError.value = err?.message || 'Generation failed'
  } finally {
    submitting.value = false
  }
}

async function copyRowCode(code) {
  await copyText(String(code || ''))
}

async function copyAllCodes() {
  if (!rows.value.length) return
  const text = rows.value.map(r => r.code).join('\n')
  await copyText(text)
}

function downloadAllCsv() {
  if (!rows.value.length) return
  const csv = toCsv(rows.value)
  const ts = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '')
  downloadCsv(`codes_${ts}.csv`, csv)
}
</script>

<template>
  <LayoutAuthenticated>
    <SectionMain>
      <SectionTitleLineWithButton :icon="mdiKeyVariant" title="Generate Codes" main />

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- ────────────── FORM ────────────── -->
        <CardBox is-form @submit.prevent="onSubmit">
          <template v-if="submitError">
            <div class="mb-4 flex items-center text-sm text-red-600">
              <BaseButton :icon="mdiAlertCircle" color="danger" rounded-full small class="mr-2 pointer-events-none" />
              <span class="break-words">{{ submitError }}</span>
            </div>
          </template>

          <FormField label="Type">
            <FormControl
              v-model="form.type"
              name="code_type"
              type="select"
              :options="[
                { id: 'oneoff',    label: 'One-off (server-generated, batch)' },
                { id: 'reusable',  label: 'Reusable (you provide the code)'   },
                { id: 'single',    label: 'Single-use (you provide the code)' },
              ]"
              required
            />
          </FormField>

          <FormField label="Function" :help="selectedFunction?.description || 'Select a function'">
            <FormControl
              v-model="form.functionKey"
              name="function"
              type="select"
              :options="functions.map(f => ({ id: f.key, label: f.label }))"
              :disabled="loadingFunctions"
              required
            />
            <div v-if="errorFunctions" class="mt-1 text-xs text-red-600">
              {{ errorFunctions }}
            </div>
          </FormField>

          <FormField label="Expiry (UTC will be sent)" help="Local date & time; converted to UTC ISO on submit">
            <FormControl
              v-model="form.expiresLocal"
              type="datetime-local"
              name="expires_at"
              placeholder="Pick date & time"
              required
            />
          </FormField>

          <template v-if="selectedTypeId === 'oneoff'">
            <FormField label="Count" help="How many codes to generate (server enforces limits)">
              <FormControl
                v-model.number="form.count"
                type="number"
                name="count"
                min="1"
                step="1"
                required
              />
            </FormField>
          </template>

          <template v-else>
            <FormField label="Code" help="Case-sensitive (you provide the value)">
              <FormControl v-model="form.code" name="code" placeholder="e.g., TEAM2025" required />
            </FormField>
          </template>

          <template #footer>
            <BaseButtons>
              <BaseButton
                type="submit"
                color="info"
                :label="submitting ? 'Generating…' : 'Generate'"
                :disabled="submitting || loadingFunctions"
              />
            </BaseButtons>
          </template>
        </CardBox>

        <!-- ────────────── RESULTS ────────────── -->
        <CardBox>
          <div class="mb-4 flex items-center justify-between">
            <div class="flex items-center text-gray-700 dark:text-gray-200">
              <BaseButton :icon="mdiTable" color="contrast" rounded-full small class="mr-2 pointer-events-none" />
              <span class="font-semibold">Results</span>
              <span class="ml-2 text-sm opacity-70">({{ rows.length }})</span>
            </div>

            <div class="flex gap-2">
              <BaseButton
                :icon="mdiContentCopy"
                color="info"
                outline
                small
                :disabled="!hasRows"
                label="Copy all codes"
                @click="copyAllCodes"
                title="Copy all codes to clipboard"
              />
              <BaseButton
                :icon="mdiDownload"
                color="info"
                outline
                small
                :disabled="!hasRows"
                label="Download CSV"
                @click="downloadAllCsv"
                title="Download CSV (code,type,function,expires_at,created_at)"
              />
            </div>
          </div>

          <div v-if="!hasRows" class="text-sm text-gray-600 dark:text-gray-300">
            No codes generated yet.
          </div>

          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead>
                <tr class="border-b border-gray-200 dark:border-slate-700 text-gray-600 dark:text-gray-300">
                  <th class="px-3 py-2">Code</th>
                  <th class="px-3 py-2">Type</th>
                  <th class="px-3 py-2">Function</th>
                  <th class="px-3 py-2">Expires at</th>
                  <th class="px-3 py-2">Created at</th>
                  <th class="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="`${r.code}-${r.created_at}`" class="border-b border-gray-100 dark:border-slate-800">
                  <td class="px-3 py-2 font-mono text-xs break-all">{{ r.code }}</td>
                  <td class="px-3 py-2">{{ r.type }}</td>
                  <td class="px-3 py-2">{{ r.function }}</td>
                  <td class="px-3 py-2">{{ r.expires_at }}</td>
                  <td class="px-3 py-2">{{ r.created_at }}</td>
                  <td class="px-3 py-2">
                    <BaseButton :icon="mdiContentCopy" color="info" outline small label="Copy" title="Copy code" @click="copyRowCode(r.code)" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardBox>
      </div>
    </SectionMain>
  </LayoutAuthenticated>
</template>
