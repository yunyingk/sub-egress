<template>
  <header class="flex flex-col md:flex-row md:items-center md:justify-between pb-6 mb-8 border-b border-slate-200 dark:border-slate-800 gap-4">
    <!-- 左侧品牌标识 -->
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

    <!-- 右侧操作区：极简互联网标准设计 -->
    <div class="flex items-center gap-3">
      <!-- 主操作：全量刷新 -->
      <button @click="$emit('refreshAll')" :disabled="syncing" 
              class="px-4 py-2 text-xs sm:text-sm font-semibold rounded-xl bg-sky-600 hover:bg-sky-500 text-white shadow-xs shadow-sky-600/20 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50">
        <i class="fa-solid fa-arrows-rotate" :class="{'fa-spin': syncing}"></i>
        <span>{{ syncing ? '正在同步...' : '全量刷新' }}</span>
      </button>

      <!-- 主题切换 -->
      <ThemeToggle />

      <!-- 用户中心就近浮出卡片 (经典互联网个人中心) -->
      <div v-if="currentUser" class="relative">
        <!-- 浮出触发按钮 -->
        <button @click="showUserMenu = !showUserMenu" 
                class="flex items-center gap-2.5 p-1.5 pr-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-750 shadow-xs transition-all cursor-pointer">
          <!-- 用户头像徽标 -->
          <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-500 to-indigo-600 text-white font-bold flex items-center justify-center text-xs shadow-xs uppercase">
            {{ currentUser.username ? currentUser.username.slice(0, 1) : 'U' }}
          </div>
          <div class="text-left hidden sm:block">
            <div class="text-xs font-bold text-slate-800 dark:text-slate-100 leading-tight">{{ currentUser.username }}</div>
            <div class="text-[10px] text-slate-400 leading-tight">
              {{ currentUser.role === 'admin' ? '系统管理员' : '普通用户' }}
            </div>
          </div>
          <i class="fa-solid fa-chevron-down text-[10px] text-slate-400 transition-transform duration-200"
             :class="{'rotate-180 text-sky-500': showUserMenu}"></i>
        </button>

        <!-- 背景遮罩 (用于点击卡片外关闭) -->
        <div v-if="showUserMenu" @click="showUserMenu = false" class="fixed inset-0 z-40 bg-transparent"></div>

        <!-- 浮出的就近用户设置卡片 -->
        <div v-if="showUserMenu" 
             @click.stop
             class="absolute right-0 top-full mt-2.5 z-50 w-72 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-700/80 overflow-hidden text-xs animate-in fade-in zoom-in-95 duration-150">
          
          <!-- 卡片头部：用户信息与专属 Token 摘要 -->
          <div class="p-4 bg-slate-50/70 dark:bg-slate-750/50">
            <div class="flex items-center gap-3">
              <div class="w-11 h-11 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 text-white font-bold flex items-center justify-center text-sm shadow-md uppercase shrink-0">
                {{ currentUser.username ? currentUser.username.slice(0, 1) : 'U' }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5">
                  <span class="text-sm font-bold text-slate-900 dark:text-white truncate">{{ currentUser.username }}</span>
                  <span v-if="currentUser.role === 'admin'" class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300 border border-purple-200 dark:border-purple-800 shrink-0">
                    管理员
                  </span>
                  <span v-else class="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300 shrink-0">
                    普通用户
                  </span>
                </div>
                <div v-if="currentUser.sub_hash_token" class="text-[11px] font-mono text-slate-400 mt-0.5 flex items-center gap-1">
                  <span>Token: {{ currentUser.sub_hash_token.slice(0, 8) }}...</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 分组 1: 个人核心设置 -->
          <div class="p-1.5 space-y-0.5">
            <!-- 个人安全中心 -->
            <button @click="showUserMenu = false; $emit('openSecurity')" 
                    class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-slate-700 dark:text-slate-200 hover:bg-sky-50 dark:hover:bg-sky-950/40 hover:text-sky-600 dark:hover:text-sky-400 transition-all cursor-pointer">
              <div class="w-7 h-7 rounded-lg bg-sky-100 dark:bg-sky-950 text-sky-600 dark:text-sky-400 flex items-center justify-center text-xs shrink-0">
                <i class="fa-solid fa-fingerprint"></i>
              </div>
              <div class="text-left flex-1 min-w-0">
                <div class="font-semibold text-xs text-slate-800 dark:text-slate-100">个人安全中心</div>
                <div class="text-[10px] text-slate-400 truncate">通行密钥、修改密码、第三方授权</div>
              </div>
            </button>

            <!-- 订阅参数设置 -->
            <button @click="showUserMenu = false; $emit('openSettings')" 
                    class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-slate-700 dark:text-slate-200 hover:bg-sky-50 dark:hover:bg-sky-950/40 hover:text-sky-600 dark:hover:text-sky-400 transition-all cursor-pointer">
              <div class="w-7 h-7 rounded-lg bg-sky-100 dark:bg-sky-950 text-sky-600 dark:text-sky-400 flex items-center justify-center text-xs shrink-0">
                <i class="fa-solid fa-sliders"></i>
              </div>
              <div class="text-left flex-1 min-w-0">
                <div class="font-semibold text-xs text-slate-800 dark:text-slate-100">订阅参数设置</div>
                <div class="text-[10px] text-slate-400 truncate">客户端内核、混合端口、自定义分流</div>
              </div>
            </button>
          </div>

          <!-- 分组 2: 管理员专属系统级控制台 (仅管理员可见) -->
          <div v-if="currentUser.role === 'admin'" class="p-1.5 space-y-0.5">
            <div class="px-3 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">系统管理专区</div>
            
            <a href="/admin?tab=users" @click="showUserMenu = false" 
               class="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 transition-all cursor-pointer">
              <div class="w-7 h-7 rounded-lg bg-purple-100 dark:bg-purple-950 text-purple-600 dark:text-purple-400 flex items-center justify-center text-xs shrink-0">
                <i class="fa-solid fa-users-gear"></i>
              </div>
              <div class="text-left flex-1 min-w-0">
                <div class="font-semibold text-xs text-slate-800 dark:text-slate-100">多租户用户管理</div>
                <div class="text-[10px] text-slate-400 truncate">租户生命周期、密码重设、封禁</div>
              </div>
            </a>

            <a href="/admin?tab=sources" @click="showUserMenu = false" 
               class="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 transition-all cursor-pointer">
              <div class="w-7 h-7 rounded-lg bg-purple-100 dark:bg-purple-950 text-purple-600 dark:text-purple-400 flex items-center justify-center text-xs shrink-0">
                <i class="fa-solid fa-network-wired"></i>
              </div>
              <div class="text-left flex-1 min-w-0">
                <div class="font-semibold text-xs text-slate-800 dark:text-slate-100">平台共享数据源</div>
                <div class="text-[10px] text-slate-400 truncate">配置向全平台广播共享的订阅源与节点</div>
              </div>
            </a>

            <a href="/admin?tab=rules" @click="showUserMenu = false" 
               class="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 transition-all cursor-pointer">
              <div class="w-7 h-7 rounded-lg bg-purple-100 dark:bg-purple-950 text-purple-600 dark:text-purple-400 flex items-center justify-center text-xs shrink-0">
                <i class="fa-solid fa-shield-halved"></i>
              </div>
              <div class="text-left flex-1 min-w-0">
                <div class="font-semibold text-xs text-slate-800 dark:text-slate-100">全局分流规则与参数</div>
                <div class="text-[10px] text-slate-400 truncate">权威直连/代理规则、全局默认内核</div>
              </div>
            </a>
          </div>

          <!-- 分组 3: 辅助链接与开发工具 -->
          <div class="p-1.5 space-y-0.5">
            <a href="/docs" target="_blank" @click="showUserMenu = false" 
               class="w-full flex items-center justify-between px-3 py-2 rounded-xl text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/60 transition-all cursor-pointer">
              <div class="flex items-center gap-2.5">
                <i class="fa-solid fa-book text-slate-400 text-xs w-4 text-center"></i>
                <span class="text-xs">API 接口文档</span>
              </div>
              <i class="fa-solid fa-arrow-up-right-from-square text-[10px] text-slate-400"></i>
            </a>
          </div>

          <!-- 分组 4: 退出登录 -->
          <div class="p-1.5">
            <button @click="showUserMenu = false; $emit('logout')" 
                    class="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-all cursor-pointer">
              <i class="fa-solid fa-right-from-bracket text-xs w-4 text-center"></i>
              <span class="font-semibold text-xs">退出当前账号</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script>
import { ref } from 'vue';
import ThemeToggle from './ThemeToggle.vue';

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
  setup() {
    const showUserMenu = ref(false);

    return {
      showUserMenu
    };
  }
};
</script>
