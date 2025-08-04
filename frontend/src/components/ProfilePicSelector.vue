<script setup>
import { computed } from 'vue'

/* ───────────────── props / emits ─────────────────────────────── */
const props = defineProps({
  /** Currently-selected numeric ID (1, 2, 3 …) */
  modelValue: {
    type: Number,
    default: 1,
  },
})
const emit = defineEmits(['update:modelValue'])

/* ───────────────── discover available PNGs at build-time ─────── */
const files = import.meta.glob('@/assets/propics/*.png', { eager: true })

/**
 * Extract numeric IDs from filenames like “…/7.png”.
 * The `eager:true` glob ensures the list is available synchronously
 * and is tree-shakable by Vite.
 */
const imageIds = Object.keys(files)
  .map((p) => {
    const m = p.match(/\/(\d+)\.png$/)
    return m ? Number(m[1]) : null
  })
  .filter((n) => n !== null)
  .sort((a, b) => a - b)

/* ───────────────── two-way binding helper ────────────────────── */
const selected = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', Number(val)),
})
</script>

<template>
  <!-- Extra bg / text classes fix invisible text on Firefox & Edge dark mode -->
  <select
    v-model="selected"
    class="form-select px-2 py-1 rounded border border-gray-300 dark:border-gray-700
           bg-white text-gray-900 dark:bg-slate-800 dark:text-gray-200"
  >
    <option
      v-for="id in imageIds"
      :key="id"
      :value="id"
      class="text-gray-900 dark:text-gray-200"
    >
      {{ id }}
    </option>
  </select>
</template>
