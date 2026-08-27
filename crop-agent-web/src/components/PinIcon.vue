<script setup lang="ts">
/**
 * 置顶图标（图钉）：替换 Element Plus 的 Location / LocationFilled（地图定位针）。
 * 参照 Material Symbols 的 push_pin 图形，提供实心/描边两种形态。
 */
withDefaults(defineProps<{ filled?: boolean }>(), { filled: false })
</script>

<template>
  <svg
    class="pin-icon"
    viewBox="0 0 24 24"
    width="1em"
    height="1em"
    aria-hidden="true"
  >
    <path
      v-if="filled"
      fill="currentColor"
      d="M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z"
    />
    <path
      v-else
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linejoin="round"
      stroke-linecap="round"
      d="M14 4v5c0 1.12.37 2.16 1 3H9c.63-.84 1-1.88 1-3V4h4m2-1H8M12 2v1m-3 5c-1.66 0-3 1.34-3 3v1.5h5.5V19l1 1.5 1-1.5v-6H19V11c0-1.66-1.34-3-3-3"
    />
  </svg>
</template>

<style scoped lang="scss">
.pin-icon {
  display: inline-block;
  vertical-align: -0.15em;
  flex: 0 0 auto;
}
</style>
