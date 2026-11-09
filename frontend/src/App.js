import { ref, onMounted } from 'vue';
import Navbar from './components/Navbar.js';
import SourceList from './components/SourceList.js';
import OutboundFeed from './components/OutboundFeed.js';
import NodePool from './components/NodePool.js';
import SettingsModal from './components/SettingsModal.js';
import AddSourceModal from './components/AddSourceModal.js';

export default {
  name: 'App',
  components: {
    Navbar,
    SourceList,
    OutboundFeed,
    NodePool,
    SettingsModal,
    AddSourceModal
  },
  setup() {
    const isDark = ref(false);
    const sources = ref([]);
    const nodes = ref([]);
    const syncing = ref(false);
    const refreshingIds = ref([]);
    const selectedTarget = ref('clash');

    // 设置状态
    const showSettingsModal = ref(false);
    const savingSettings = ref(false);
    const settings = ref({
      sub_hash_token: 'e699ffd91845385075b27d813b8590df40375c6af2c4eb77',
      require_token: false,
      default_target: 'clash',
      update_interval: '12',
      write_api_token: ''
    });

    // 添加源状态
    const showAddModal = ref(false);
    const creatingSource = ref(false);

    // 主题逻辑：默认明亮白色，记忆在 localStorage
    const initTheme = () => {
      const savedTheme = localStorage.getItem('sub_egress_theme') || 'light';
      isDark.value = (savedTheme === 'dark');
      applyTheme();
    };

    const toggleTheme = () => {
      isDark.value = !isDark.value;
      localStorage.setItem('sub_egress_theme', isDark.value ? 'dark' : 'light');
      applyTheme();
    };

    const applyTheme = () => {
      if (isDark.value) {
        document.documentElement.classList.add('dark');
        document.documentElement.classList.remove('light');
      } else {
        document.documentElement.classList.remove('dark');
        document.documentElement.classList.add('light');
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
          settings.value = data;
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
        }
      } catch (e) {
        console.error('Failed to save settings', e);
      } finally {
        savingSettings.value = false;
      }
    };

    onMounted(() => {
      initTheme();
      fetchSources();
      fetchNodes();
      fetchSettings();
    });

    return {
      isDark,
      toggleTheme,
      sources,
      nodes,
      syncing,
      refreshingIds,
      selectedTarget,
      settings,
      showSettingsModal,
      savingSettings,
      showAddModal,
      creatingSource,
      refreshAll,
      refreshSource,
      deleteSource,
      createSource,
      saveSettings
    };
  },
  template: `
    <div class="max-w-7xl mx-auto px-4 py-8">
      <Navbar 
        :is-dark="isDark" 
        :syncing="syncing"
        @toggle-theme="toggleTheme" 
        @open-settings="showSettingsModal = true" 
        @refresh-all="refreshAll" 
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

      <!-- 底部：合并节点池大盘 -->
      <NodePool :nodes="nodes" />

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
    </div>
  `
};
