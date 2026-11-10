<template>
  <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 w-full p-6 md:p-8 flex flex-col space-y-6">
    <!-- 头部说明与操作区 -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-slate-200 dark:border-slate-700 gap-4 shrink-0">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 flex items-center justify-center">
          <i class="fa-solid fa-network-wired text-lg"></i>
        </div>
        <div>
          <h3 class="text-lg font-bold text-slate-900 dark:text-white">平台共享数据源管控</h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">在此统一配置向全平台所有用户广播下发的共享节点源与上游数据</p>
        </div>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <!-- 范围切换器: 共享源 vs 全量租户源 -->
        <div class="flex items-center bg-slate-100 dark:bg-slate-700 p-0.5 rounded-lg text-xs">
          <button @click="switchScope('shared')" 
                  :class="scope === 'shared' ? 'bg-white dark:bg-slate-600 text-purple-600 dark:text-purple-300 font-bold shadow-xs' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700'"
                  class="px-2.5 py-1.5 rounded-md transition-all cursor-pointer">
            仅共享源
          </button>
          <button @click="switchScope('all')" 
                  :class="scope === 'all' ? 'bg-white dark:bg-slate-600 text-purple-600 dark:text-purple-300 font-bold shadow-xs' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700'"
                  class="px-2.5 py-1.5 rounded-md transition-all cursor-pointer"
                  title="租户隔离审计模式：查看系统内所有用户的源归属">
            全量源 (审计)
          </button>
        </div>

        <button @click="fetchSources" :disabled="loading" 
                class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
          <i class="fa-solid fa-arrows-rotate" :class="{'fa-spin': loading}"></i>刷新
        </button>

        <button @click="openAddModal" 
                class="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-purple-600 hover:bg-purple-500 text-white shadow-xs transition-all flex items-center gap-1.5 cursor-pointer">
          <i class="fa-solid fa-plus"></i>添加平台共享源
        </button>
      </div>
    </div>

    <!-- 提示消息栏 -->
    <div v-if="message" class="p-3.5 rounded-xl border text-xs flex items-center justify-between gap-2 shrink-0 transition-all"
         :class="isError ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300' : 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'">
      <div class="flex items-center gap-2">
        <i class="fa-solid" :class="isError ? 'fa-circle-exclamation text-rose-500' : 'fa-circle-check text-emerald-500'"></i>
        <span>{{ message }}</span>
      </div>
      <button @click="message = ''" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 cursor-pointer">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>

    <!-- 架构隔离安全提示卡片 -->
    <div class="p-4 rounded-xl bg-purple-50/70 dark:bg-purple-950/30 border border-purple-200 dark:border-purple-800/50 text-xs text-purple-900 dark:text-purple-200 flex items-start gap-3">
      <i class="fa-solid fa-shield-halved text-purple-600 dark:text-purple-400 mt-0.5 text-sm shrink-0"></i>
      <div class="leading-relaxed space-y-1">
        <div><strong>租户数据隐私与共享管控准则：</strong></div>
        <div>1. <strong>平台共享源</strong>：在此统一配置向全平台广播下发的基础设施源，由管理员全权增删改查；</div>
        <div>2. <strong>租户私有源</strong>：用户前台录入的源属于<strong>租户个人资产与严格隐私</strong>，管理员<strong>无权编辑且绝不能将其转为公有</strong>；在审计模式下仅保留异常刷新与违规清理删除权限。</div>
      </div>
    </div>

    <!-- 列表展示区域 -->
    <div class="space-y-3">
      <div v-if="loading && sources.length === 0" class="p-12 text-center text-slate-400 text-sm">
        <i class="fa-solid fa-circle-notch fa-spin text-2xl text-purple-500 mb-2 block"></i>
        <span>正在加载上游数据源...</span>
      </div>

      <div v-else-if="sources.length === 0" class="p-12 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 text-center text-slate-400 text-sm">
        暂无已配置的平台共享源，请点击右上角「添加平台共享源」进行录入。
      </div>

      <div v-else class="grid grid-cols-1 gap-3">
        <div v-for="src in sources" :key="src.id" 
             class="p-4 rounded-xl border border-slate-200 dark:border-slate-700/80 bg-slate-50/60 dark:bg-slate-750/50 hover:border-slate-300 dark:hover:border-slate-600 transition-all space-y-3">
          <div class="flex items-start justify-between gap-3 flex-wrap">
            <div class="space-y-1 min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-slate-900 dark:text-white text-base">{{ src.name }}</span>
                <span :class="src.is_shared ? 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300 border-purple-300 dark:border-purple-800' : 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 border-sky-300 dark:border-sky-800'"
                      class="px-2 py-0.5 text-xs font-semibold rounded-md border flex items-center gap-1">
                  <i class="fa-solid" :class="src.is_shared ? 'fa-globe' : 'fa-user-lock'"></i>
                  {{ src.is_shared ? '平台公共共享' : `租户私有 [${src.owner_username}]` }}
                </span>
                <span :class="src.status === 'healthy' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/80 dark:text-emerald-300 dark:border-emerald-800' : 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/80 dark:text-rose-300 dark:border-rose-800'"
                      class="px-2 py-0.5 text-xs rounded border font-mono">
                  {{ src.status === 'healthy' ? '正常' : '异常' }}
                </span>
                <span class="text-xs text-slate-500 dark:text-slate-400 font-mono bg-white dark:bg-slate-700 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-600">
                  {{ src.node_count }} 节点
                </span>
                <span v-if="!src.enabled" class="text-xs text-amber-600 dark:text-amber-400 font-medium bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 rounded border border-amber-200 dark:border-amber-800">
                  已停用
                </span>
              </div>

              <div class="text-xs font-mono text-slate-500 dark:text-slate-400 truncate" :title="src.url">
                {{ maskUrl(src.url) }}
              </div>
            </div>

            <!-- 操作按钮组 -->
            <div class="flex items-center gap-1.5 shrink-0">
              <button @click="refreshSource(src.id)" 
                      :disabled="refreshingIds.includes(src.id)" 
                      class="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-white dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1 cursor-pointer disabled:opacity-50"
                      title="手动拉取并重新解析节点">
                <i class="fa-solid fa-rotate-right" :class="{'fa-spin': refreshingIds.includes(src.id)}"></i>
                <span>刷新</span>
              </button>

              <!-- 仅平台公共共享源允许管理员编辑；租户私有源为用户隐私，严禁管理员编辑或转为公有 -->
              <button v-if="src.is_shared" 
                      @click="openEditModal(src)" 
                      class="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-white dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1 cursor-pointer">
                <i class="fa-solid fa-pen-to-square"></i>
                <span>编辑</span>
              </button>
              <div v-else 
                   class="px-2 py-1 text-[11px] text-slate-400 dark:text-slate-500 rounded bg-slate-100 dark:bg-slate-700/60 flex items-center gap-1 cursor-help" 
                   title="租户私有数据源：涉及租户个人隐私，管理员无权直接编辑或转化为共享源，仅支持运维刷新或违规删除。">
                <i class="fa-solid fa-user-lock text-[10px]"></i>
                <span>私有·不可编辑</span>
              </div>

              <button @click="deleteSource(src)" 
                      class="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-rose-200 dark:border-rose-900/60 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-rose-600 dark:text-rose-400 transition-all flex items-center gap-1 cursor-pointer"
                      :title="src.is_shared ? '删除平台共享源' : '以管理员身份删除此违规/废弃的租户私有源'">
                <i class="fa-solid fa-trash-can"></i>
                <span>删除</span>
              </button>
            </div>
          </div>

          <!-- 底部流量与到期时间统计 -->
          <div class="pt-2 border-t border-slate-200/60 dark:border-slate-700/60 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 flex-wrap gap-2">
            <div class="flex items-center gap-2">
              <span v-if="src.traffic_total > 0">
                已用: <strong class="text-slate-800 dark:text-slate-200 font-mono">{{ formatBytes(src.traffic_used) }}</strong> / {{ formatBytes(src.traffic_total) }}
              </span>
              <span v-else>无流量配额上限</span>
              <span v-if="src.reset_info" class="text-sky-600 dark:text-sky-400">({{ src.reset_info }})</span>
            </div>
            <div class="font-mono text-[11px]">
              最后同步: {{ src.last_sync_at ? formatDate(src.last_sync_at) : '从未' }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加 / 编辑共享源 Modal -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div class="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl max-w-lg w-full p-6 space-y-5">
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-700 pb-3">
          <h3 class="font-bold text-base text-slate-900 dark:text-white flex items-center gap-2">
            <i class="fa-solid fa-network-wired text-purple-600 dark:text-purple-400"></i>
            <span>{{ isEditing ? '编辑数据源' : '新增平台共享数据源' }}</span>
          </h3>
          <button @click="showModal = false" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 cursor-pointer">
            <i class="fa-solid fa-xmark text-lg"></i>
          </button>
        </div>

        <div class="space-y-4 text-xs">
          <div>
            <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1 flex items-center justify-between">
              <span>订阅链接 / 节点协议 URL</span>
              <span v-if="isProbing" class="text-purple-600 dark:text-purple-400 text-[10px] font-normal flex items-center gap-1">
                <i class="fa-solid fa-spinner fa-spin"></i> 正在智能探测名称与节点...
              </span>
            </label>
            <input v-model="form.url" 
                   @blur="triggerProbe"
                   type="text" 
                   placeholder="https://... 或 ss://... (粘贴后自动识别名称)" 
                   class="w-full px-3 py-2 font-mono rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500">
            
            <div v-if="probeInfo" class="mt-1.5 px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200/80 dark:border-emerald-800/60 text-[11px] text-emerald-700 dark:text-emerald-300 flex items-center justify-between">
              <span class="flex items-center gap-1.5 truncate">
                <i class="fa-solid fa-circle-check text-emerald-500 shrink-0"></i>
                <span class="truncate">已自动识别: <strong>{{ probeInfo.suggested_name }}</strong></span>
              </span>
              <span class="font-mono text-[10px] shrink-0 bg-emerald-100 dark:bg-emerald-900/60 px-1.5 py-0.5 rounded font-bold">
                {{ probeInfo.node_count }} 节点
              </span>
            </div>
          </div>

          <div>
            <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">
              源名称 (备注)
              <span class="text-[10px] font-normal text-slate-400">(填入链接后自动填入，亦可手动修改)</span>
            </label>
            <input v-model="form.name" type="text" placeholder="例如: 平台主力香港专线 / 美国住宅宽带" 
                   class="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500">
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">解析协议格式</label>
              <select v-model="form.source_type" 
                      class="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500">
                <option value="auto">自动识别 (Clash YAML / Base64 / URI)</option>
                <option value="remote_clash">Clash YAML 订阅</option>
                <option value="remote_base64">Base64 / 节点列表</option>
                <option value="local_yaml">本地 YAML 内容</option>
              </select>
            </div>

            <div>
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">启用状态</label>
              <select v-model="form.enabled" 
                      class="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500">
                <option :value="true">正常启用 (自动接入调度池)</option>
                <option :value="false">暂停停用 (不参与出站调度)</option>
              </select>
            </div>
          </div>

          <!-- 平台共享属性说明 (不再提供转公/转私选择，严格遵循共享专区职责) -->
          <div class="p-3 rounded-xl bg-purple-50/60 dark:bg-purple-950/30 border border-purple-200/70 dark:border-purple-800/40 text-[11px] text-purple-800 dark:text-purple-300 flex items-start gap-2">
            <i class="fa-solid fa-globe text-purple-600 dark:text-purple-400 mt-0.5 shrink-0"></i>
            <span>此数据源为<strong>全平台公共基础设施</strong>（is_shared = true），保存后将自动广播下发至所有合法租户的客户端订阅与出站大盘中。</span>
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-700">
          <button @click="showModal = false" class="px-4 py-2 text-xs font-medium rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition cursor-pointer">
            取消
          </button>
          <button @click="handleSave" :disabled="saving || !form.name.trim() || !form.url.trim()" 
                  class="px-4 py-2 text-xs font-bold rounded-xl bg-purple-600 hover:bg-purple-500 text-white shadow-xs transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
            <i class="fa-solid fa-check" :class="{'fa-spin': saving}"></i>
            <span>{{ saving ? '正在同步落库...' : '确认保存' }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue';
import { formatBytes, formatDate, maskUrl } from '../utils/format.js';

export default {
  name: 'AdminSources',
  props: {
    currentAdmin: { type: Object, required: true }
  },
  setup() {
    const sources = ref([]);
    const loading = ref(false);
    const saving = ref(false);
    const scope = ref('shared');
    const message = ref('');
    const isError = ref(false);
    const refreshingIds = ref([]);

    const showModal = ref(false);
    const isEditing = ref(false);
    const editingId = ref(null);
    const isProbing = ref(false);
    const probeInfo = ref(null);
    let probeTimer = null;
    let autoFilledName = '';

    const form = ref({
      name: '',
      url: '',
      source_type: 'auto',
      enabled: true,
      is_shared: true
    });

    const triggerProbe = async () => {
      const targetUrl = (form.value.url || '').trim();
      if (!targetUrl || targetUrl.length < 8) return;
      if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) return;

      isProbing.value = true;
      try {
        const resp = await fetch('/api/sources/probe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ url: targetUrl })
        });
        if (resp.ok) {
          const data = await resp.json();
          probeInfo.value = data;
          if (data.suggested_name) {
            if (!form.value.name.trim() || form.value.name === autoFilledName) {
              form.value.name = data.suggested_name;
              autoFilledName = data.suggested_name;
            }
          }
        }
      } catch (err) {
        console.debug('Probe subscription error', err);
      } finally {
        isProbing.value = false;
      }
    };

    watch(() => form.value.url, (newVal) => {
      if (isEditing.value) return;
      if (probeTimer) clearTimeout(probeTimer);
      if (!newVal || newVal.trim().length < 10) {
        probeInfo.value = null;
        return;
      }
      probeTimer = setTimeout(() => {
        triggerProbe();
      }, 500);
    });

    const setNotice = (msg, err = false) => {
      message.value = msg;
      isError.value = err;
      if (!err) {
        setTimeout(() => {
          if (message.value === msg) message.value = '';
        }, 5000);
      }
    };

    const fetchSources = async () => {
      loading.value = true;
      try {
        const res = await fetch(`/api/admin/sources?scope=${scope.value}`);
        if (res.ok) {
          sources.value = await res.json();
        } else {
          const data = await res.json().catch(() => ({}));
          setNotice(data.detail || '获取共享数据源失败', true);
        }
      } catch (e) {
        setNotice('网络请求异常，无法加载上游源', true);
      } finally {
        loading.value = false;
      }
    };

    const switchScope = (newScope) => {
      scope.value = newScope;
      fetchSources();
    };

    const openAddModal = () => {
      isEditing.value = false;
      editingId.value = null;
      probeInfo.value = null;
      autoFilledName = '';
      form.value = {
        name: '',
        url: '',
        source_type: 'auto',
        enabled: true,
        is_shared: true
      };
      showModal.value = true;
    };

    const openEditModal = (src) => {
      if (!src.is_shared) {
        setNotice('租户私有订阅源受隐私保护，管理员无权直接编辑或转化为共享源，仅支持刷新或违规删除。', true);
        return;
      }
      isEditing.value = true;
      editingId.value = src.id;
      form.value = {
        name: src.name,
        url: src.url,
        source_type: src.source_type || 'auto',
        enabled: src.enabled !== false,
        is_shared: true
      };
      showModal.value = true;
    };

    const handleSave = async () => {
      if (!form.value.name.trim() || !form.value.url.trim()) return;
      saving.value = true;
      try {
        const url = isEditing.value ? `/api/admin/sources/${editingId.value}` : '/api/admin/sources';
        const method = isEditing.value ? 'PUT' : 'POST';
        const res = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form.value)
        });
        if (res.ok) {
          setNotice(isEditing.value ? '共享源已成功更新！' : '平台共享源已成功创建并完成首次同步！');
          showModal.value = false;
          await fetchSources();
        } else {
          const data = await res.json().catch(() => ({}));
          setNotice(data.detail || '保存失败', true);
        }
      } catch (e) {
        setNotice('网络异常，保存失败', true);
      } finally {
        saving.value = false;
      }
    };

    const refreshSource = async (id) => {
      refreshingIds.value.push(id);
      try {
        const res = await fetch(`/api/admin/sources/${id}/refresh`, { method: 'POST' });
        if (res.ok) {
          setNotice('源节点已成功刷新并重解析！');
          await fetchSources();
        } else {
          const data = await res.json().catch(() => ({}));
          setNotice(data.detail || '刷新节点失败', true);
        }
      } catch (e) {
        setNotice('网络请求异常，刷新失败', true);
      } finally {
        refreshingIds.value = refreshingIds.value.filter(item => item !== id);
      }
    };

    const deleteSource = async (src) => {
      const confirmMsg = src.is_shared
        ? `确定要彻底删除平台共享源「${src.name}」吗？\n删除后全平台所有用户的对应节点池都将被移除。`
        : `确定以管理员身份移除租户 [${src.owner_username}] 的私有订阅源「${src.name}」吗？\n此操作将同时清理该源下所有已解析的物理节点。`;
      if (!confirm(confirmMsg)) return;
      try {
        const res = await fetch(`/api/admin/sources/${src.id}`, { method: 'DELETE' });
        if (res.ok) {
          setNotice(`已成功删除源「${src.name}」`);
          await fetchSources();
        } else {
          const data = await res.json().catch(() => ({}));
          setNotice(data.detail || '删除失败', true);
        }
      } catch (e) {
        setNotice('网络异常，删除失败', true);
      }
    };

    onMounted(() => {
      fetchSources();
    });

    return {
      sources,
      loading,
      saving,
      scope,
      message,
      isError,
      refreshingIds,
      showModal,
      isEditing,
      isProbing,
      probeInfo,
      triggerProbe,
      form,
      switchScope,
      fetchSources,
      openAddModal,
      openEditModal,
      handleSave,
      refreshSource,
      deleteSource,
      formatBytes,
      formatDate,
      maskUrl
    };
  }
};
</script>
