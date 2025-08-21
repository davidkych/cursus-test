<script setup>
import { useAuth } from '@/stores/auth.js'
import UserAvatar from '@/components/UserAvatar.vue'

/**
 * Size in px for the rendered avatar.
 * Default keeps the top-bar avatar small (tweak if your original was different).
 */
const props = defineProps({
  size: {
    type: [Number, String],
    default: 40, // original top-bar size (adjust if your theme used e.g. 36 or 48)
  },
})

const auth = useAuth()
</script>

<template>
  <UserAvatar
    :username="auth.displayName || 'Guest'"
    :avatar="auth.avatarUrl"
    :size="size"
  >
    <slot />
  </UserAvatar>
</template>
