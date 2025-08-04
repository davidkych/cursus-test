<script setup>
// ── layout / wrapper components ────────────────────────────────
import LayoutGuest       from '@/layouts/LayoutGuest.vue'
import SectionFullScreen from '@/components/SectionFullScreen.vue'

// ── discover every *.png in the propics folder at build-time ──
const files = import.meta.glob('@/assets/propics/*.png', {
  eager: true,
  import: 'default', // we only need the URL string
})

/**
 * Build a sorted array like [{ id: 7, src: '/assets/propics/7.png' }, …]
 */
const images = Object.entries(files)
  .map(([path, src]) => {
    const m = path.match(/\/(\d+)\.png$/)
    return m ? { id: Number(m[1]), src } : null
  })
  .filter(Boolean)
  .sort((a, b) => a.id - b.id)
</script>

<template>
  <LayoutGuest>
    <SectionFullScreen v-slot="{ cardClass }" bg="purplePink">
      <!-- white ⟷ dark-slate card wrapper -->
      <div
        :class="[cardClass, 'bg-white dark:bg-slate-800 rounded-lg shadow-lg']"
        class="p-6 overflow-y-auto max-h-[80vh]"
      >
        <h1
          class="text-xl font-semibold mb-6 text-center text-gray-900 dark:text-gray-100"
        >
          Available Profile Pictures
        </h1>

        <div
          class="grid gap-6 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6"
        >
          <div
            v-for="img in images"
            :key="img.id"
            class="flex flex-col items-center"
          >
            <!-- keep square aspect & crop to circle -->
            <img
              :src="img.src"
              :alt="`Avatar ${img.id}`"
              class="w-32 h-32 rounded-full border border-gray-200 dark:border-gray-600 object-cover object-center"
            />
            <span class="mt-2 text-sm text-gray-700 dark:text-gray-300">
              {{ img.id }}
            </span>
          </div>
        </div>
      </div>
    </SectionFullScreen>
  </LayoutGuest>
</template>
