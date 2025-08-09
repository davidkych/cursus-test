<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { mdiClose, mdiDotsVertical } from '@mdi/js'
import { containerMaxW } from '@/config.js'
import BaseIcon from '@/components/BaseIcon.vue'
import NavBarMenuList from '@/components/NavBarMenuList.vue'
import NavBarItemPlain from '@/components/NavBarItemPlain.vue'
import { useAuth } from '@/stores/auth.js'

const props = defineProps({
  menu: {
    type: Array,
    required: true,
  },
})

const emit = defineEmits(['menu-click'])

const router = useRouter()
const auth = useAuth()

const isMenuNavBarActive = ref(false)

/**
 * Keep the structure of the incoming menu, but if an item is flagged
 * `isCurrentUser`, replace its `label` with the authenticated username.
 * This avoids touching NavBarMenuList.vue and removes the hardcoded
 * "John Doe" that came from the sample store.
 */
const menuResolved = computed(() =>
  (props.menu || []).map((it) =>
    it && it.isCurrentUser
      ? { ...it, label: auth.displayName || it.label || 'User' }
      : it,
  ),
)

const menuClick = (event, item) => {
  // Intercept logout and perform real sign-out
  if (item && item.isLogout) {
    event?.preventDefault?.()
    auth.logout()
    isMenuNavBarActive.value = false
    router.replace('/login')
    return
  }
  emit('menu-click', event, item)
}
</script>

<template>
  <nav
    class="top-0 inset-x-0 fixed bg-gray-50 h-14 z-30 transition-position w-screen lg:w-auto dark:bg-slate-800"
  >
    <div class="flex lg:items-stretch" :class="containerMaxW">
      <div class="flex flex-1 items-stretch h-14">
        <slot />
      </div>

      <!-- Mobile menu toggle -->
      <div class="flex-none items-stretch flex h-14 lg:hidden">
        <NavBarItemPlain @click.prevent="isMenuNavBarActive = !isMenuNavBarActive">
          <BaseIcon :path="isMenuNavBarActive ? mdiClose : mdiDotsVertical" size="24" />
        </NavBarItemPlain>
      </div>

      <!-- The menu list (contains the current user item and logout) -->
      <div
        class="max-h-screen-menu overflow-y-auto lg:overflow-visible absolute w-screen top-14 left-0 bg-gray-50 shadow-lg lg:w-auto lg:flex lg:static lg:shadow-none dark:bg-slate-800"
        :class="[isMenuNavBarActive ? 'block' : 'hidden']"
      >
        <NavBarMenuList :menu="menuResolved" @menu-click="menuClick" />
      </div>
    </div>
  </nav>
</template>
