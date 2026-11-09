import ThemeToggle from './ThemeToggle.js';

export default {
  name: 'Navbar',
  components: {
    ThemeToggle
  },
  props: {
    syncing: { type: Boolean, default: false },
    version: { type: String, default: '' },
    currentUser: { type: Object, default: () => null }
  },
  emits: ['openSettings', 'openSecurity', 'openAdmin', 'refreshAll', 'logout'],
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
              <span v-if="version" class="text-xs text-slate-400 font-mono">{{ version }}</span>
            </div>
            <p class="text-sm text-slate-500 dark:text-slate-400">出站网关 · 多内核订阅聚合调度 · 二元制单选中心</p>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <!-- 现代主流外观切换组件 (浅色 / 深色 / 跟随系统) -->
        <ThemeToggle />

        <!-- 管理员专属后台管理页签 -->
        <button v-if="currentUser && currentUser.role === 'admin'" 
                @click="$emit('openAdmin')" 
                class="px-3.5 py-2 text-sm font-medium rounded-lg border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/60 shadow-xs transition-all flex items-center gap-2">
          <i class="fa-solid fa-users-gear text-purple-500"></i>
          <span>用户管理</span>
        </button>

        <!-- 个人安全中心 (通行密钥与密码) -->
        <button v-if="currentUser" 
                @click="$emit('openSecurity')" 
                class="px-3 py-2 text-sm font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 shadow-xs transition-all flex items-center gap-2">
          <i class="fa-solid fa-fingerprint text-sky-500"></i>
          <span class="hidden sm:inline">安全中心</span>
        </button>

        <!-- 读写与安全设置 -->
        <button @click="$emit('openSettings')" 
                class="px-3.5 py-2 text-sm font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 shadow-xs transition-all flex items-center gap-2">
          <i class="fa-solid fa-sliders text-sky-500"></i>
          <span>订阅参数</span>
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

        <!-- 用户名徽章与退出登录 -->
        <div v-if="currentUser" class="flex items-center pl-2 border-l border-slate-200 dark:border-slate-700 gap-2">
          <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300">
            <i class="fa-regular fa-user text-slate-400"></i>
            <span>{{ currentUser.username }}</span>
          </div>
          <button @click="$emit('logout')" title="退出登录" 
                  class="p-2 text-slate-400 hover:text-rose-500 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-all">
            <i class="fa-solid fa-right-from-bracket"></i>
          </button>
        </div>
      </div>
    </header>
  `
};
