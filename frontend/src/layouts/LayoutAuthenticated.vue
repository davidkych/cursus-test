<script setup>
import {
  mdiForwardburger,
  mdiBackburger,
  mdiMenu,
  mdiAccountCog,
} from '@mdi/js'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import menuAside from '@/menuAside.js'
import menuAsideAdmin from '@/menuAsideAdmin.js'
import menuNavBar from '@/menuNavBar.js'
import { useDarkModeStore } from '@/stores/darkMode.js'
import BaseIcon from '@/components/BaseIcon.vue'
import FormControl from '@/components/FormControl.vue'
import NavBar from '@/components/NavBar.vue'
import NavBarItemPlain from '@/components/NavBarItemPlain.vue'
import AsideMenu from '@/components/AsideMenu.vue'
import FooterBar from '@/components/FooterBar.vue'

const layoutAsidePadding = 'xl:pl-60'

const darkModeStore = useDarkModeStore()
const router = useRouter()

const isAsideMobileExpanded = ref(false)
const isAsideLgActive   = ref(false)
const isAdminMode       = ref(false)          // ← admin/user toggle

router.beforeEach(() => {
  isAsideMobileExpanded.value = false
  isAsideLgActive.value = false
})

const currentMenu = computed(() =>
  isAdminMode.value ? menuAsideAdmin : menuAside,
)

const menuClick = (_, item) => {
  if (item.isToggleLightDark) darkModeStore.set()
  if (item.isLogout) {
    /* placeholder */
  }
}
</script>

<template>
  <div :class="{ 'overflow-hidden lg:overflow-visible': isAsideMobileExpanded }">
    <div
      :class="[layoutAsidePadding, { 'ml-60 lg:ml-0': isAsideMobileExpanded }]"
      class="pt-14 min-h-screen w-screen transition-position lg:w-auto bg-gray-50 dark:bg-slate-800 dark:text-slate-100"
    >
      <!-- ────────────── TOP NAVBAR ────────────── -->
      <NavBar
        :menu="menuNavBar"
        :class="[layoutAsidePadding, { 'ml-60 lg:ml-0': isAsideMobileExpanded }]"
        @menu-click="menuClick"
      >
        <!-- burger (mobile) -->
        <NavBarItemPlain
          display="flex lg:hidden"
          @click.prevent="isAsideMobileExpanded = !isAsideMobileExpanded"
        >
          <BaseIcon
            :path="isAsideMobileExpanded ? mdiBackburger : mdiForwardburger"
            size="24"
          />
        </NavBarItemPlain>

        <!-- burger (desktop small) -->
        <NavBarItemPlain
          display="hidden lg:flex xl:hidden"
          @click.prevent="isAsideLgActive = true"
        >
          <BaseIcon :path="mdiMenu" size="24" />
        </NavBarItemPlain>

        <!-- search -->
        <NavBarItemPlain use-margin>
          <FormControl
            placeholder="Search (ctrl+k)"
            ctrl-k-focus
            transparent
            borderless
          />
        </NavBarItemPlain>

        <!-- ADMIN / USER TOGGLE  -->
        <NavBarItemPlain
          class="cursor-pointer select-none"
          @click.prevent="isAdminMode = !isAdminMode"
          :title="isAdminMode ? 'Switch to user view' : 'Switch to admin view'"
        >
          <BaseIcon :path="mdiAccountCog" size="24" />
          <!-- small label shows on md+ screens -->
          <span class="ml-1 hidden md:inline text-sm">
            {{ isAdminMode ? 'Admin' : 'User' }}
          </span>
        </NavBarItemPlain>
      </NavBar>

      <!-- ────────────── SIDE MENU ────────────── -->
      <AsideMenu
        :is-aside-mobile-expanded="isAsideMobileExpanded"
        :is-aside-lg-active="isAsideLgActive"
        :menu="currentMenu"
        @menu-click="menuClick"
        @aside-lg-close-click="isAsideLgActive = false"
      />

      <!-- main page content -->
      <slot />

      <!-- footer -->
      <FooterBar>
        Get more with&nbsp;
        <a
          href="https://tailwind-vue.justboil.me/"
          target="_blank"
          class="text-blue-600"
        >
          Premium version
        </a>
      </FooterBar>
    </div>
  </div>
</template>
