<template>
  <!-- 管理后台独立全屏大盘 (/admin?tab=users | /admin?tab=rules) -->
  <div v-if="isAdminRoute" class="max-w-7xl mx-auto px-4 py-8">
    <!-- 管理员未就绪或鉴权加载状态 -->
    <div v-if="!currentUser" class="flex flex-col items-center justify-center min-h-[50vh] text-slate-400">
      <i class="fa-solid fa-circle-notch fa-spin text-3xl mb-3 text-purple-500"></i>
      <span class="text-sm font-medium">正在校验管理员权限...</span>
    </div>

    <!-- 非管理员权限拦截卡片 -->
    <div v-else-if="currentUser.role !== 'admin'" class="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 p-8 text-center max-w-md mx-auto mt-16 space-y-4">
      <div class="w-14 h-14 rounded-2xl bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 flex items-center justify-center mx-auto text-2xl shadow-inner">
        <i class="fa-solid fa-lock"></i>
      </div>
      <h3 class="text-lg font-bold text-slate-900 dark:text-white">访问权限受限</h3>
      <p class="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
        当前登录账号 <strong class="text-slate-800 dark:text-slate-200">[{{ currentUser.username }}]</strong> 不具备管理员权限，无法访问系统管理控制台。
      </p>
      <div class="pt-2">
        <button @click="navigateHome" class="w-full py-2.5 px-4 text-xs font-semibold rounded-xl bg-slate-900 hover:bg-slate-800 text-white transition-all cursor-pointer">
          返回调度中枢首页
        </button>
      </div>
    </div>

    <!-- 管理员控制台主体大盘 -->
    <div v-else class="space-y-6">
      <!-- 统一风格顶部导航栏 -->
      <header class="flex flex-col md:flex-row md:items-center md:justify-between pb-6 border-b border-slate-200 dark:border-slate-800 gap-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center shadow-md shadow-purple-500/20 text-white text-lg">
            <i class="fa-solid fa-users-gear"></i>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">sub-egress 管理控制台</h1>
              <span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300 border border-purple-300 dark:border-purple-800 flex items-center gap-1">
                <i class="fa-solid fa-shield-halved text-[10px]"></i> 管理员专属
              </span>
              <span v-if="appVersion" class="text-xs text-slate-400 font-mono">{{ appVersion }}</span>
            </div>
            <p class="text-sm text-slate-500 dark:text-slate-400">多租户生命周期管控 · 全局订阅参数 · 权威分流规则中枢</p>
          </div>
        </div>

        <div class="flex items-center gap-2.5 flex-wrap">
          <ThemeToggle />

          <!-- 返回前台调度中枢 -->
          <button @click="navigateHome" 
                  class="px-3.5 py-2 text-sm font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 shadow-xs transition-all flex items-center gap-2 cursor-pointer">
            <i class="fa-solid fa-arrow-left text-sky-500"></i>
            <span>返回调度中枢</span>
          </button>

          <!-- 管理员身份标签 -->
          <div class="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-purple-50 dark:bg-purple-950/40 border border-purple-200 dark:border-purple-800 text-xs font-bold text-purple-700 dark:text-purple-300">
            <i class="fa-solid fa-user-shield"></i>
            <span>{{ currentUser.username }}</span>
          </div>

          <!-- 退出登录 -->
          <button @click="handleLogout" title="退出登录" 
                  class="p-2 text-slate-400 hover:text-rose-500 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-all cursor-pointer">
            <i class="fa-solid fa-right-from-bracket"></i>
          </button>
        </div>
      </header>

      <!-- 三级 Tab 导航切换器: ?tab=users vs ?tab=sources vs ?tab=rules -->
      <div class="flex items-center gap-2 p-1.5 bg-slate-100 dark:bg-slate-800/80 rounded-2xl border border-slate-200 dark:border-slate-700 w-fit">
        <button @click="switchAdminTab('users')" 
                :class="adminTab === 'users' ? 'bg-white dark:bg-slate-700 text-purple-600 dark:text-purple-400 font-bold shadow-xs' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
                class="px-4 py-2 text-xs sm:text-sm rounded-xl transition-all flex items-center gap-2 cursor-pointer">
          <i class="fa-solid fa-users-gear text-sm"></i>
          <span>用户与租户管理</span>
        </button>
        <button @click="switchAdminTab('sources')" 
                :class="adminTab === 'sources' ? 'bg-white dark:bg-slate-700 text-purple-600 dark:text-purple-400 font-bold shadow-xs' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
                class="px-4 py-2 text-xs sm:text-sm rounded-xl transition-all flex items-center gap-2 cursor-pointer">
          <i class="fa-solid fa-network-wired text-sm"></i>
          <span>平台共享数据源</span>
        </button>
        <button @click="switchAdminTab('rules')" 
                :class="adminTab === 'rules' ? 'bg-white dark:bg-slate-700 text-purple-600 dark:text-purple-400 font-bold shadow-xs' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
                class="px-4 py-2 text-xs sm:text-sm rounded-xl transition-all flex items-center gap-2 cursor-pointer">
          <i class="fa-solid fa-sliders text-sm"></i>
          <span>全局规则与设置</span>
        </button>
      </div>

      <!-- Tab 1: 用户管理 -->
      <AdminPanel v-if="adminTab === 'users'" :visible="true" :current-admin="currentUser" @close="navigateHome" />

      <!-- Tab 2: 平台共享数据源 -->
      <AdminSources v-else-if="adminTab === 'sources'" :current-admin="currentUser" />

      <!-- Tab 3: 全局规则与设置 -->
      <AdminRules v-else-if="adminTab === 'rules'" />
    </div>
  </div>

  <div v-else class="max-w-7xl mx-auto px-4 py-8">
      <Navbar 
        :version="appVersion"
        :syncing="syncing"
        :current-user="currentUser"
        @open-settings="showSettingsModal = true" 
        @open-security="showSecurityModal = true"
        @open-admin="navigateAdmin"
        @refresh-all="refreshAll" 
        @logout="handleLogout"
      />

      <!-- 主工作区：上游数据源与下游分发中心 -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-10">
        <div class="lg:col-span-6">
          <SourceList 
            :sources="sources" 
            :refreshing-ids="refreshingIds"
            @open-add-modal="showAddModal = true"
            @refresh-source="refreshSource"
            @delete-source="deleteSource"
          />
        </div>

        <div class="lg:col-span-6">
          <OutboundFeed 
            :settings="settings"
            v-model:selected-target="selectedTarget"
            @open-settings="showSettingsModal = true"
          />
        </div>
      </div>

      <!-- 底部：合并节点池大盘 (聚合动态策略组 + 物理透传平铺，支持折叠) -->
      <NodePool :nodes="nodes" :dynamic-groups="dynamicGroups" />

      <!-- 设置与添加源模态弹窗 -->
      <SettingsModal 
        :visible="showSettingsModal"
        :settings="settings"
        :saving="savingSettings"
        @close="showSettingsModal = false"
        @save="saveSettings"
      />

      <AddSourceModal 
        :visible="showAddModal"
        :creating="creatingSource"
        @close="showAddModal = false"
        @create="createSource"
      />

      <!-- 个人安全中心弹窗 (通行密钥与密码) -->
      <UserSecurityModal 
        :visible="showSecurityModal"
        :user="currentUser"
        @close="showSecurityModal = false"
        @user-updated="fetchCurrentUser"
      />

      <!-- 管理员专属后台管理弹窗 -->
    </div>
  
</template>

<script>
import { ref, computed, onMounted } from 'vue';
import Navbar from './components/Navbar.vue';
import SourceList from './components/SourceList.vue';
import OutboundFeed from './components/OutboundFeed.vue';
import NodePool from './components/NodePool.vue';
import SettingsModal from './components/SettingsModal.vue';
import AddSourceModal from './components/AddSourceModal.vue';
import UserSecurityModal from './components/UserSecurityModal.vue';
import AdminPanel from './components/AdminPanel.vue';
import AdminRules from './components/AdminRules.vue';
import AdminSources from './components/AdminSources.vue';
import ThemeToggle from './components/ThemeToggle.vue';

export default {
  name: 'App',
  components: {
    Navbar,
    SourceList,
    OutboundFeed,
    NodePool,
    SettingsModal,
    AddSourceModal,
    UserSecurityModal,
    AdminPanel,
    AdminRules,
    AdminSources,
    ThemeToggle
  },
  setup() {
    const currentUser = ref(null);
    const isAdminRoute = computed(() => {
      const p = window.location.pathname;
      return p === '/admin' || p.startsWith('/admin/');
    });

    const getInitialAdminTab = () => {
      const p = window.location.pathname;
      if (p === '/admin/rules') return 'rules';
      if (p === '/admin/sources') return 'sources';
      if (p === '/admin/users') return 'users';
      const params = new URLSearchParams(window.location.search);
      const tab = params.get('tab');
      if (tab === 'rules' || tab === 'sources' || tab === 'users') return tab;
      return 'users';
    };

    const adminTab = ref(getInitialAdminTab());

    const switchAdminTab = (tab) => {
      adminTab.value = tab;
      window.history.pushState(null, '', `/admin?tab=${tab}`);
    };

    const navigateAdmin = (tab = 'users') => {
      if (isAdminRoute.value) {
        switchAdminTab(tab);
      } else {
        window.location.href = `/admin?tab=${tab}`;
      }
    };

    const navigateHome = () => { window.location.href = '/'; };
    const sources = ref([]);
    const nodes = ref([]);
    const dynamicGroups = ref([]);
    const syncing = ref(false);
    const refreshingIds = ref([]);
    const selectedTarget = ref('clash');

    // 模态弹窗状态
    const showSettingsModal = ref(false);
    const showSecurityModal = ref(false);
    const showAdminModal = ref(false);
    const showAddModal = ref(false);
    const savingSettings = ref(false);
    const creatingSource = ref(false);

    const settings = ref({
      sub_hash_token: 'e699ffd91845385075b27d813b8590df40375c6af2c4eb77',
      require_token: false,
      default_target: 'clash',
      update_interval: '12',
      write_api_token: '',
      subscription_title: 'sub-egress',
      clash_mixed_port: '7897',
      clash_terminal_port: '7898'
    });

    // 服务端下发版本号
    const appVersion = computed(() => {
      return settings.value?.version ? `v${settings.value.version}` : '';
    });

    // 鉴权与获取当前登录用户
    const fetchCurrentUser = async () => {
      try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
          currentUser.value = await res.json();
          // 同步用户专属的 Token 和配置
          if (currentUser.value.sub_hash_token) {
            settings.value.sub_hash_token = currentUser.value.sub_hash_token;
          }
          if (currentUser.value.subscription_title) {
            settings.value.subscription_title = currentUser.value.subscription_title;
          }
          if (currentUser.value.clash_mixed_port) {
            settings.value.clash_mixed_port = currentUser.value.clash_mixed_port;
          }
          if (currentUser.value.clash_terminal_port) {
            settings.value.clash_terminal_port = currentUser.value.clash_terminal_port;
          }
          if (currentUser.value.custom_direct_domains !== undefined) {
            settings.value.custom_direct_domains = currentUser.value.custom_direct_domains;
          }
          if (currentUser.value.custom_proxy_domains !== undefined) {
            settings.value.custom_proxy_domains = currentUser.value.custom_proxy_domains;
          }
          if (currentUser.value.custom_rules !== undefined) {
            settings.value.custom_rules = currentUser.value.custom_rules;
          }
        } else if (res.status === 401) {
          // 未登录，自动重定向到独立登录页 (无 html 后缀)
          window.location.href = '/login';
        }
      } catch (e) {
        console.error('Failed to fetch user', e);
      }
    };

    // 数据加载
    const fetchSources = async () => {
      try {
        const res = await fetch('/api/sources');
        if (res.ok) {
          sources.value = await res.json();
        }
      } catch (e) {
        console.error('Failed to load sources', e);
      }
    };

    const fetchNodes = async () => {
      try {
        const res = await fetch('/api/nodes');
        if (res.ok) {
          const data = await res.json();
          nodes.value = data.nodes || [];
          dynamicGroups.value = data.dynamic_groups || [];
        }
      } catch (e) {
        console.error('Failed to load nodes', e);
      }
    };

    const fetchSettings = async () => {
      try {
        const res = await fetch('/api/settings');
        if (res.ok) {
          const data = await res.json();
          settings.value = { ...settings.value, ...data };
          if (data.default_target) {
            selectedTarget.value = data.default_target;
          }
        }
      } catch (e) {
        console.error('Failed to load settings', e);
      }
    };

    // 操作
    const refreshAll = async () => {
      syncing.value = true;
      try {
        for (const s of sources.value) {
          await fetch(`/api/sources/${s.id}/refresh`, { method: 'POST' });
        }
        await Promise.all([fetchSources(), fetchNodes()]);
      } catch (e) {
        console.error('Failed to refresh all', e);
      } finally {
        syncing.value = false;
      }
    };

    const refreshSource = async (id) => {
      refreshingIds.value.push(id);
      try {
        await fetch(`/api/sources/${id}/refresh`, { method: 'POST' });
        await Promise.all([fetchSources(), fetchNodes()]);
      } catch (e) {
        console.error(`Failed to refresh source ${id}`, e);
      } finally {
        refreshingIds.value = refreshingIds.value.filter(item => item !== id);
      }
    };

    const deleteSource = async (id) => {
      if (!confirm('确定要删除此上游源吗？相关的平铺物理节点也将一并移除。')) return;
      try {
        await fetch(`/api/sources/${id}`, { method: 'DELETE' });
        await Promise.all([fetchSources(), fetchNodes()]);
      } catch (e) {
        console.error(`Failed to delete source ${id}`, e);
      }
    };

    const createSource = async (formData) => {
      creatingSource.value = true;
      try {
        const res = await fetch('/api/sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData)
        });
        if (res.ok) {
          showAddModal.value = false;
          await Promise.all([fetchSources(), fetchNodes()]);
        }
      } catch (e) {
        console.error('Failed to create source', e);
      } finally {
        creatingSource.value = false;
      }
    };

    const saveSettings = async (newSettings) => {
      savingSettings.value = true;
      try {
        const personalSettings = Object.fromEntries(
          ['sub_hash_token', 'subscription_title', 'clash_mixed_port', 'clash_terminal_port', 'custom_direct_domains', 'custom_proxy_domains', 'custom_rules']
            .filter((key) => newSettings[key] !== undefined)
            .map((key) => [key, newSettings[key]])
        );
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(personalSettings)
        });
        if (res.ok) {
          settings.value = JSON.parse(JSON.stringify(newSettings));
          if (newSettings.default_target) {
            selectedTarget.value = newSettings.default_target;
          }
          showSettingsModal.value = false;
          await fetchCurrentUser();
        }
      } catch (e) {
        console.error('Failed to save settings', e);
      } finally {
        savingSettings.value = false;
      }
    };

    const handleLogout = async () => {
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch (e) {}
      window.location.href = '/login';
    };

    onMounted(async () => {
      window.addEventListener('popstate', () => {
        adminTab.value = getInitialAdminTab();
      });
      await fetchCurrentUser();
      fetchSources();
      fetchNodes();
      fetchSettings();
    });

    return {
      currentUser,
      isAdminRoute,
      adminTab,
      switchAdminTab,
      navigateAdmin,
      navigateHome,
      sources,
      nodes,
      dynamicGroups,
      syncing,
      refreshingIds,
      selectedTarget,
      settings,
      showSettingsModal,
      showSecurityModal,
      showAdminModal,
      savingSettings,
      showAddModal,
      creatingSource,
      appVersion,
      fetchCurrentUser,
      refreshAll,
      refreshSource,
      deleteSource,
      createSource,
      saveSettings,
      handleLogout
    };
  }
};
</script>
