<script setup lang="ts">
import AppSidebar from '@/components/AppSidebar.vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()

const nav = [
  { path: '/chat', label: '对话', icon: 'ChatDotRound' },
  { path: '/knowledge', label: '知识库', icon: 'Collection' },
  { path: '/history', label: '历史', icon: 'Clock' },
]
</script>

<template>
  <div class="app-shell">
    <!-- 侧边栏：桌面固定栏 / 移动端抽屉（由 AppSidebar 内部处理） -->
    <AppSidebar :nav="nav" />

    <div class="main">
      <!-- 移动端顶栏：汉堡菜单呼出侧边栏（全局视觉规范·响应式） -->
      <header class="mobile-topbar">
        <button
          class="hamburger"
          aria-label="打开菜单"
          @click="store.mobileSidebarOpen = true"
        >
          <el-icon><Menu /></el-icon>
        </button>
        <span class="topbar-brand">🌾 禾知</span>
      </header>

      <main class="content">
        <router-view />
      </main>
    </div>

    <nav class="bottom-nav">
      <router-link
        v-for="item in nav"
        :key="item.path"
        :to="item.path"
        class="bottom-item"
        active-class="active"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <!-- 移动端抽屉遮罩 -->
    <transition name="fade">
      <div
        v-if="store.mobileSidebarOpen"
        class="mobile-mask"
        @click="store.mobileSidebarOpen = false"
      ></div>
    </transition>
  </div>
</template>

<style scoped lang="scss">
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ---------- 主内容 ---------- */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.content {
  flex: 1;
  min-width: 0;
  overflow: auto;
}

/* ---------- 移动端顶栏（默认隐藏） ---------- */
.mobile-topbar {
  display: none;
}

/* ---------- 底部 Tab（移动端） ---------- */
.bottom-nav {
  display: none;
}

/* ---------- 移动端：顶栏 + 汉堡菜单 + 抽屉遮罩 ---------- */
@media (max-width: 767px) {
  .mobile-topbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    background: #fff;
    border-bottom: 1px solid #eef1ea;
  }

  .hamburger {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: none;
    border-radius: var(--radius-sm);
    background: #f2f5ef;
    color: var(--crop-green);
    font-size: 18px;
    cursor: pointer;
    transition: background 150ms var(--ease);

    &:hover {
      background: #e8f3e4;
    }
  }

  .topbar-brand {
    font-size: 18px;
    font-weight: 700;
    color: var(--crop-green);
  }

  .mobile-mask {
    position: fixed;
    inset: 0;
    background: rgba(31, 61, 29, 0.35);
    z-index: 200;
  }

  .fade-enter-active,
  .fade-leave-active {
    transition: opacity 200ms var(--ease);
  }

  .fade-enter-from,
  .fade-leave-to {
    opacity: 0;
  }

  .bottom-nav {
    display: flex;
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    height: 60px;
    background: #fff;
    border-top: 1px solid #eef1ea;
    z-index: 100;
  }

  .bottom-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    font-size: 12px;
    color: #8a9785;
    text-decoration: none;

    &.active {
      color: var(--crop-green);
    }
  }

  .content {
    padding-bottom: 72px;
  }
}
</style>
