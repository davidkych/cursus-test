<script setup>
import { mdiUpload } from '@mdi/js'
import { computed, ref, watch } from 'vue'
import BaseButton from '@/components/BaseButton.vue'

const props = defineProps({
  modelValue: {
    // Single File (default) or Array<File> when multiple=true
    type: [Object, File, Array, null],
    default: null,
  },
  label: {
    type: String,
    default: null,
  },
  icon: {
    type: String,
    default: mdiUpload,
  },
  accept: {
    type: String,
    default: null,
  },
  color: {
    type: String,
    default: 'info',
  },
  isRoundIcon: Boolean,

  // ⟨NEW⟩
  name: { type: String, default: null },
  multiple: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'change'])

const root = ref(null) // native <input type="file">

// Internal mirror of modelValue for filename display
const file = ref(props.modelValue)

// Show filename area when not round icon and we have a selection
const showFilename = computed(() => !props.isRoundIcon && !!file.value)

// Keep internal state in sync with v-model
const modelValueProp = computed(() => props.modelValue)
watch(modelValueProp, (value) => {
  file.value = value
  if (!value && root.value) {
    // root is the <input>, not a component
    root.value.value = null
  }
})

// Friendly filename text (first file name; indicates "+N more" if multiple)
const filenameText = computed(() => {
  const v = file.value
  if (!v) return ''
  if (Array.isArray(v)) {
    if (v.length === 0) return ''
    return v.length > 1 ? `${v[0]?.name || 'file'} + ${v.length - 1} more` : (v[0]?.name || '')
  }
  return v?.name || ''
})

function upload(event) {
  const list = event?.target?.files || event?.dataTransfer?.files || []
  const files = Array.from(list)

  // For v-model: single File by default; array of Files when multiple=true
  file.value = props.multiple ? files : (files[0] || null)

  emit('update:modelValue', file.value)
  // Also emit a generic change event so callers can hook into it
  emit('change', event, files)
}
</script>

<template>
  <div class="flex items-stretch justify-start relative">
    <label class="inline-flex">
      <BaseButton
        as="a"
        :class="{ 'w-12 h-12': isRoundIcon, 'rounded-r-none': showFilename }"
        :icon-size="isRoundIcon ? 24 : undefined"
        :label="isRoundIcon ? null : label"
        :icon="icon"
        :color="color"
        :rounded-full="isRoundIcon"
        :disabled="disabled"
      />
      <input
        ref="root"
        type="file"
        class="absolute top-0 left-0 w-full h-full opacity-0 outline-hidden cursor-pointer -z-1"
        :name="name || undefined"
        :accept="accept || undefined"
        :multiple="multiple"
        :disabled="disabled"
        @change="upload"
        @input="upload"  <!-- keep for backward-compat -->
      />
    </label>
    <div
      v-if="showFilename"
      class="px-4 py-2 bg-gray-100 dark:bg-slate-800 border-gray-200 dark:border-slate-700 border rounded-r"
    >
      <span class="text-ellipsis line-clamp-1">
        {{ filenameText }}
      </span>
    </div>
  </div>
</template>
