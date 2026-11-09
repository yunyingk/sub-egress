import { ref, computed, onMounted } from 'vue';
import Navbar from './components/Navbar.js';
import SourceList from './components/SourceList.js';
import OutboundFeed from './components/OutboundFeed.js';
import NodePool from './components/NodePool.js';
import SettingsModal from './components/SettingsModal.js';
import AddSourceModal from './components/AddSourceModal.js';
import UserSecurityModal from './components/UserSecurityModal.js';
import AdminPanel from './components/AdminPanel.js';

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
    AdminPanel
  },
  setup() {
    const currentUser = ref(null);
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
        } else if (res.status === 401) {
          // 未登录，自动重定向到独立登录页
          window.location.href = '/login.html';
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
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newSettings)
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
      window.location.href = '/login.html';
    };

    onMounted(async () => {
      await fetchCurrentUser();
      fetchSources();
      fetchNodes();
      fetchSettings();
    });

    return {
      currentUser,
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
  },
  template: `
    <div class="max-w-7xl mx-auto px-4 py-8">
      <Navbar 
        :version="appVersion"
        :syncing="syncing"
        :current-user="currentUser"
        @open-settings="showSettingsModal = true" 
        @open-security="showSecurityModal = true"
        @open-admin="showAdminModal = true"
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
      <AdminPanel 
        v-if="currentUser && currentUser.role === 'admin'"
        :visible="showAdminModal"
        :current-admin="currentUser"
        @close="showAdminModal = false"
      />
    </div>
  `
};
