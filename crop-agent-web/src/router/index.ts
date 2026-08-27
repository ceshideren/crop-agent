/*
 * @Author: Donghao Chen
 * @LastEditors: Donghao Chen
 * @Description: 
 */
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/chat' },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('../views/ChatView.vue'),
    meta: { title: '对话' },
  },
  {
    path: '/group/:id',
    name: 'group-detail',
    component: () => import('../views/GroupDetailView.vue'),
    meta: { title: '分组详情' },
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: () => import('../views/KnowledgeBase.vue'),
    meta: { title: '知识库' },
  },
  {
    path: '/knowledge/preview/:docId',
    name: 'knowledge-preview',
    component: () => import('../views/KnowledgePreview.vue'),
    meta: { title: '文档预览' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
