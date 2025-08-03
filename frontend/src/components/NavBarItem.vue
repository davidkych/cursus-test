<script setup>
import { mdiChevronUp, mdiChevronDown } from '@mdi/js'
import { RouterLink } from 'vue-router'
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import BaseIcon                   from '@/components/BaseIcon.vue'
import UserAvatarCurrentUser      from '@/components/UserAvatarCurrentUser.vue'
import NavBarMenuList             from '@/components/NavBarMenuList.vue'
import BaseDivider                from '@/components/BaseDivider.vue'

/* ───────────────────────── props & emits ───────────────────────── */
const props = defineProps({
  item: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['menu-click'])

/* ───────────────────────── element type ────────────────────────── */
const is = computed(() => {
  if (props.item.href) return 'a'
  if (props.item.to)   return RouterLink
  return 'div'
})

/* ───────────────────────── css classes ─────────────────────────── */
const isDropdownActive = ref(false)

const componentClass = computed(() => {
  const base = [
    isDropdownActive.value
      ? 'navbar-item-label-active dark:text-slate-400'
      : 'navbar-item-label dark:text-white dark:hover:text-slate-400',
    props.item.menu ? 'lg:py-2 lg:px-3' : 'py-2 px-3',
  ]
  if (props.item.isDesktopNoLabel) base.push('lg:w-16', 'lg:justify-center')
  return base
})

/* ───────────────────────── label & avatar ──────────────────────── */
const itemLabel  = computed(() => props.item.label)               // auth.store already injected the username
const avatarUrl  = computed(() => (props.item.isCurrentUser ? props.item.avatar : null))

/* ───────────────────────── click handlers ──────────────────────── */
const menuClick = (event) => {
  emit('menu-click', event, props.item)
  if (props.item.menu) isDropdownActive.value = !isDropdownActive.value
}

const menuClickDropdown = (event, item) => {
  emit('menu-click', event, item)
}

/* ───────────────────────── outside-click close ─────────────────── */
const root = ref(null)
const forceClose = (event) => {
  if (root.value && !root.value.contains(event.target)) {
    isDropdownActive.value = false
  }
}

onMounted(() => {
  if (props.item.menu) window.addEventListener('click', forceClose)
})
onBeforeUnmount(() => {
  if (props.item.menu) window.removeEventListener('click', forceClose)
})
</script>

<template>
  <BaseDivider v-if="item.isDivider" nav-bar />
  <component
    :is="is"
    v-else
    ref="root"
    class="block lg:flex items-center relative cursor-pointer"
    :class="componentClass"
    :to="item.to ?? null"
    :href="item.href ?? null"
    :target="item.target ?? null"
    @click="menuClick"
  >
    <div
      class="flex items-center"
      :class="{
        'bg-gray-100 dark:bg-slate-800 lg:bg-transparent lg:dark:bg-transparent p-3 lg:p-0':
          item.menu,
      }"
    >
      <!-- avatar (current user) -->
      <img
        v-if="item.isCurrentUser && avatarUrl"
        :src="avatarUrl"
        class="w-6 h-6 rounded-full mr-3 inline-flex object-cover"
        alt="avatar"
      />
      <UserAvatarCurrentUser
        v-else-if="item.isCurrentUser"
        class="w-6 h-6 mr-3 inline-flex"
      />

      <!-- icon -->
      <BaseIcon v-if="item.icon" :path="item.icon" class="transition-colors" />

      <!-- label -->
      <span
        class="px-2 transition-colors"
        :class="{ 'lg:hidden': item.isDesktopNoLabel && item.icon }"
      >
        {{ itemLabel }}
      </span>

      <!-- dropdown chevron -->
      <BaseIcon
        v-if="item.menu"
        :path="isDropdownActive ? mdiChevronUp : mdiChevronDown"
        class="hidden lg:inline-flex transition-colors"
      />
    </div>

    <!-- dropdown menu -->
    <div
      v-if="item.menu"
      class="text-sm border-b border-gray-100 lg:border lg:bg-white lg:absolute lg:top-full lg:left-0 lg:min-w-full lg:z-20 lg:rounded-lg lg:shadow-lg lg:dark:bg-slate-800 dark:border-slate-700"
      :class="{ 'lg:hidden': !isDropdownActive }"
    >
      <NavBarMenuList :menu="item.menu" @menu-click="menuClickDropdown" />
    </div>
  </component>
</template>
