<script setup>
import { computed } from 'vue'

const props = defineProps({
  username: {
    type: String,
    required: true,
  },
  avatar: {
    type: String,
    default: null,
  },
  api: {
    type: String,
    default: 'avataaars',
  },
  /**
   * Fixed rendered size (in px). Accepts number (e.g. 96) or string ('96', '96px').
   * Keeps uploaded images (even huge ones) within this circle.
   */
  size: {
    type: [Number, String],
    default: 96, // change once here to alter the default avatar size
  },
})

const avatar = computed(
  () =>
    props.avatar ??
    `https://api.dicebear.com/7.x/${props.api}/svg?seed=${props.username.replace(
      /[^a-z0-9]+/gi,
      '-',
    )}.svg`,
)

const username = computed(() => props.username)

const sizeNum = computed(() => {
  const v = props.size
  if (typeof v === 'number' && isFinite(v) && v > 0) return Math.round(v)
  const n = parseInt(String(v).replace(/[^\d]/g, '') || '0', 10)
  return n > 0 ? n : 96
})

const boxStyle = computed(() => ({
  width: `${sizeNum.value}px`,
  height: `${sizeNum.value}px`,
}))
</script>

<template>
  <div class="inline-block">
    <img
      :src="avatar"
      :alt="username"
      :width="sizeNum"
      :height="sizeNum"
      :style="boxStyle"
      class="rounded-full object-cover object-center bg-gray-100 dark:bg-slate-800"
      loading="lazy"
      decoding="async"
    />
    <slot />
  </div>
</template>
