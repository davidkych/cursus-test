<script setup>
import { useAuth } from '@/stores/auth.js'
import UserAvatar from '@/components/UserAvatar.vue'

/**
 * Switch from main store (sample data) to real auth store.
 * Keeps the external API of this wrapper the same: it still renders <UserAvatar>
 * and forwards slots, but sources the current user's name & avatar from auth.
 */
const auth = useAuth()
</script>

<template>
  <UserAvatar
    :username="auth.displayName || 'Guest'"
    :avatar="auth.avatarUrl"
  >
    <slot />
  </UserAvatar>
</template>
