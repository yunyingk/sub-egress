import ThemeToggle from './ThemeToggle.js';

export default {
  name: 'Navbar',
  components: {
    ThemeToggle
  },
  props: {
    syncing: { type: Boolean, default: false },
    version: { type: String, default: 'v0.2.11' }
  },
  emits: ['openSettings', 'refreshAll'],
  template: `
    <header class="flex flex-col md:flex-row md:items-center md:justify-between pb-6 mb-8 border-b border-slate-200 dark:border-slate-800 gap-4">
      <div>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-500 to-blue-600 flex items-center justify-center shadow-md shadow-sky-500/20">
            <i class="fa-solid fa-satellite-dish text-white text-lg"></i>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">sub-egress</h1>
              <span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> 服务就绪
              </span>
              <span class="text-xs text-slate-400 font-mono">{{ version }}</span>
            </div>
            <p class="text-sm text-slate-500 dark:text-slate-400">出站网关 · 多内核订阅聚合调度 · 二元制单选中心</p>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <!-- 现代主流外观切换组件 (浅色 / 深色 / 跟随系统) -->
        <ThemeToggle />

        <!-- 读写与安全设置 -->
        <button @click="$emit('openSettings')" 
                class="px-3.5 py-2 text-sm font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 shadow-xs transition-all flex items-center gap-2">
          <i class="fa-solid fa-sliders text-sky-500"></i>
          <span>读写设置</span>
        </button>

        <!-- API 文档 -->
        <a href="/docs" target="_blank" 
           class="px-3 py-2 text-sm font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 shadow-xs transition-all flex items-center gap-2">
          <i class="fa-solid fa-book text-slate-400"></i>
          <span>API</span>
        </a>

        <!-- 全量刷新 -->
        <button @click="$emit('refreshAll')" :disabled="syncing" 
                class="px-4 py-2 text-sm font-medium rounded-lg bg-sky-600 hover:bg-sky-500 text-white shadow-xs shadow-sky-600/20 transition-all flex items-center gap-2 disabled:opacity-50">
          <i class="fa-solid fa-arrows-rotate" :class="{'fa-spin': syncing}"></i>
          <span>{{ syncing ? '正在同步...' : '全量刷新' }}</span>
        </button>
      </div>
    </header>
  `
};
