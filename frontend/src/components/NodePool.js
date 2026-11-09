import { ref, computed } from 'vue';

export default {
  name: 'NodePool',
  props: {
    nodes: { type: Array, required: true },
    dynamicGroups: { type: Array, default: () => [] }
  },
  setup(props) {
    const isMasterCollapsed = ref(localStorage.getItem('sub_egress_nodepool_master_collapsed') === 'true');
    const isPhysicalCollapsed = ref(localStorage.getItem('sub_egress_nodepool_physical_collapsed') !== 'false');
    const searchQuery = ref('');
    const selectedCountry = ref('ALL');
    const selectedGroup = ref(null);
    const sortByLatency = ref(false);

    // 延迟测速状态管理（前端即时缓存 + 后端数据库双向联动）
    const initialLatencies = (() => {
      try {
        return JSON.parse(localStorage.getItem('sub_egress_node_latencies') || '{}');
      } catch (e) {
        return {};
      }
    })();
    const nodeLatencies = ref(initialLatencies);
    const testingNodeIds = ref(new Set());
    const isBatchTesting = ref(false);

    const saveLatencies = () => {
      try {
        localStorage.setItem('sub_egress_node_latencies', JSON.stringify(nodeLatencies.value));
      } catch (e) {}
    };

    const isTestingNode = (id) => testingNodeIds.value.has(id);

    // 优先读取前端即时测速结果，未手动测速时直接读取后端定时巡检任务入库的延迟数据
    const getNodeLatency = (id) => {
      const mem = nodeLatencies.value[id] || nodeLatencies.value[String(id)];
      if (mem && mem.latency !== undefined) return mem.latency;
      const n = props.nodes.find(item => item.id === id);
      return n && n.latency !== undefined ? n.latency : null;
    };

    const getNodeStatus = (id) => {
      const mem = nodeLatencies.value[id] || nodeLatencies.value[String(id)];
      if (mem && mem.status) return mem.status;
      const n = props.nodes.find(item => item.id === id);
      return n ? n.latency_status : null;
    };

    const formatNodeLatency = (id) => {
      if (isTestingNode(id)) return '测速中...';
      const lat = getNodeLatency(id);
      if (lat !== null && lat !== undefined) {
        return `${lat} ms`;
      }
      const st = getNodeStatus(id);
      if (st === 'timeout') return '超时';
      if (st === 'refused') return '拒绝';
      if (st && st !== 'ok') return '不可达';
      return '测延迟';
    };

    const getLatencyBadgeClass = (id) => {
      if (isTestingNode(id)) {
        return 'bg-sky-50 text-sky-600 border-sky-300 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-800 animate-pulse';
      }
      const lat = getNodeLatency(id);
      const st = getNodeStatus(id);
      if (lat !== null && lat !== undefined) {
        if (lat < 250) {
          return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800 hover:bg-emerald-100';
        }
        if (lat < 500) {
          return 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-800 hover:bg-sky-100';
        }
        return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800 hover:bg-amber-100';
      }
      if (st && st !== 'ok') {
        return 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950 dark:text-rose-300 dark:border-rose-800 hover:bg-rose-100';
      }
      return 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700 hover:bg-sky-50 hover:text-sky-600 hover:border-sky-300 dark:hover:bg-sky-950 dark:hover:text-sky-300';
    };

    // 前端手动点测单个节点（触发后端即时握手测速并就地更新 DB 与界面）
    const pingSingleNode = async (node) => {
      if (testingNodeIds.value.has(node.id)) return;
      testingNodeIds.value.add(node.id);
      try {
        const resp = await fetch(`/api/nodes/${node.id}/ping`, { 
          method: 'POST',
          credentials: 'include'
        });
        if (resp.ok) {
          const data = await resp.json();
          nodeLatencies.value = {
            ...nodeLatencies.value,
            [String(node.id)]: {
              latency: data.latency,
              status: data.status,
              time: Date.now()
            }
          };
          saveLatencies();
        }
      } catch (err) {
        nodeLatencies.value = {
          ...nodeLatencies.value,
          [String(node.id)]: {
            latency: null,
            status: 'error',
            time: Date.now()
          }
        };
      } finally {
        testingNodeIds.value.delete(node.id);
      }
    };

    // 批量并发测速（支持测试当前展示/筛选的节点）
    const pingCurrentFilteredNodes = async () => {
      if (isBatchTesting.value) return;
      const targetList = filteredNodes.value;
      if (!targetList.length) return;

      isBatchTesting.value = true;
      const ids = targetList.map(n => n.id);
      ids.forEach(id => testingNodeIds.value.add(id));

      try {
        const resp = await fetch('/api/nodes/ping', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ node_ids: ids })
        });
        if (resp.ok) {
          const data = await resp.json();
          nodeLatencies.value = {
            ...nodeLatencies.value,
            ...data.results
          };
          saveLatencies();
        }
      } catch (err) {
        console.error('Batch ping error:', err);
      } finally {
        ids.forEach(id => testingNodeIds.value.delete(id));
        isBatchTesting.value = false;
      }
    };

    // 获取动态组的最佳延迟
    const getGroupBestLatency = (grp) => {
      if (!grp.proxies || !grp.proxies.length) return null;
      let minLat = null;
      for (const proxyName of grp.proxies) {
        const matched = props.nodes.find(n => n.display_name === proxyName);
        if (matched) {
          const lat = getNodeLatency(matched.id);
          if (lat !== null && lat !== undefined) {
            if (minLat === null || lat < minLat) {
              minLat = lat;
            }
          }
        }
      }
      return minLat;
    };

    const toggleMasterCollapse = () => {
      isMasterCollapsed.value = !isMasterCollapsed.value;
      localStorage.setItem('sub_egress_nodepool_master_collapsed', isMasterCollapsed.value ? 'true' : 'false');
    };

    const togglePhysicalCollapse = () => {
      isPhysicalCollapsed.value = !isPhysicalCollapsed.value;
      localStorage.setItem('sub_egress_nodepool_physical_collapsed', isPhysicalCollapsed.value ? 'true' : 'false');
    };

    const countryStats = computed(() => {
      const stats = {};
      for (const n of props.nodes) {
        const cc = n.country_code || 'OTHER';
        stats[cc] = (stats[cc] || 0) + 1;
      }
      return stats;
    });

    const getCountryFlag = (cc) => {
      const n = props.nodes.find(item => item.country_code === cc);
      return n ? n.country_flag : '🌐';
    };

    const filterByGroup = (grp) => {
      if (selectedGroup.value && selectedGroup.value.name === grp.name) {
        selectedGroup.value = null;
      } else {
        selectedGroup.value = grp;
        selectedCountry.value = 'ALL';
        isPhysicalCollapsed.value = false; // 自动展开平铺节点以便用户核对成员
      }
    };

    const filteredNodes = computed(() => {
      let list = props.nodes.filter(n => {
        // 如果激活了动态组筛选
        if (selectedGroup.value && selectedGroup.value.proxies) {
          if (!selectedGroup.value.proxies.includes(n.display_name)) {
            return false;
          }
        }
        // 国家筛选
        if (selectedCountry.value !== 'ALL' && n.country_code !== selectedCountry.value) {
          return false;
        }
        // 关键字搜索
        if (searchQuery.value) {
          const q = searchQuery.value.toLowerCase();
          return (
            (n.display_name && n.display_name.toLowerCase().includes(q)) ||
            (n.server && n.server.toLowerCase().includes(q)) ||
            (n.node_type && n.node_type.toLowerCase().includes(q)) ||
            (n.source_name && n.source_name.toLowerCase().includes(q))
          );
        }
        return true;
      });

      if (sortByLatency.value) {
        list = [...list].sort((a, b) => {
          const latA = getNodeLatency(a.id);
          const latB = getNodeLatency(b.id);
          if (latA !== null && latB !== null) return latA - latB;
          if (latA !== null) return -1;
          if (latB !== null) return 1;
          return 0;
        });
      }

      return list;
    });

    return {
      isMasterCollapsed,
      toggleMasterCollapse,
      isPhysicalCollapsed,
      togglePhysicalCollapse,
      searchQuery,
      selectedCountry,
      selectedGroup,
      sortByLatency,
      filterByGroup,
      countryStats,
      getCountryFlag,
      filteredNodes,
      isTestingNode,
      getNodeLatency,
      getNodeStatus,
      formatNodeLatency,
      getLatencyBadgeClass,
      pingSingleNode,
      pingCurrentFilteredNodes,
      isBatchTesting,
      getGroupBestLatency
    };
  },
  template: `
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 shadow-xs space-y-5">
      <!-- 顶部头部：标题、统计与大盘总折叠按钮 -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 dark:border-slate-700/60 pb-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white font-bold shadow-xs">
            <i class="fa-solid fa-network-wired text-base"></i>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h3 class="text-base font-bold text-slate-900 dark:text-white">合并节点池大盘 (Active Node Pool)</h3>
              <span class="px-2 py-0.5 text-xs rounded-full bg-sky-50 text-sky-700 dark:bg-sky-950/80 dark:text-sky-300 border border-sky-200 dark:border-sky-800 font-mono font-medium">
                ⚡ {{ dynamicGroups.length }} 动态组 · 🌐 {{ nodes.length }} 节点
              </span>
            </div>
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">后端每 5 分钟定时自动巡检测速，支持前端单节点点测与批量实时测速</p>
          </div>
        </div>

        <!-- 右侧操作区：搜索与整卡折叠按钮 -->
        <div class="flex items-center gap-2">
          <!-- 搜索框（展开时展示） -->
          <div v-show="!isMasterCollapsed && !isPhysicalCollapsed" class="relative">
            <i class="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-xs text-slate-400"></i>
            <input v-model="searchQuery" type="text" placeholder="搜索节点名/地区/协议..." 
                   class="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-sky-500 w-44">
          </div>

          <button @click="toggleMasterCollapse" 
                  type="button"
                  class="px-3.5 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                  :title="isMasterCollapsed ? '展开查看大盘全部内容' : '折叠收起整个大盘卡片'">
            <i class="fa-solid text-xs text-sky-500" :class="isMasterCollapsed ? 'fa-chevron-down' : 'fa-chevron-up'"></i>
            <span>{{ isMasterCollapsed ? '展开大盘' : '折叠收起' }}</span>
          </button>
        </div>
      </div>

      <!-- 大盘全折叠状态下的轻量级概览条 -->
      <div v-if="isMasterCollapsed" 
           @click="toggleMasterCollapse" 
           class="cursor-pointer p-4 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-900/40 hover:bg-slate-100/70 dark:hover:bg-slate-900/70 transition flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-sky-100 dark:bg-sky-950/80 text-sky-600 dark:text-sky-400 flex items-center justify-center font-bold text-xs">
            <i class="fa-solid fa-layer-group"></i>
          </div>
          <div>
            <div class="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2">
              <span>节点大盘已收起</span>
              <span class="px-2 py-0.5 text-[11px] rounded bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300 border border-sky-200 dark:border-sky-800 font-mono">
                ⚡ {{ dynamicGroups.length }} 聚合动态组
              </span>
              <span class="px-2 py-0.5 text-[11px] rounded bg-slate-200/80 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-mono">
                🌐 {{ nodes.length }} 物理透传节点
              </span>
            </div>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">点击此处随时展开查看 10 个聚合动态组与平铺节点</p>
          </div>
        </div>
        <span class="text-xs font-semibold text-sky-600 dark:text-sky-400 flex items-center gap-1 hover:underline">
          展开大盘 <i class="fa-solid fa-chevron-down text-[10px]"></i>
        </span>
      </div>

      <!-- 展开状态下的内容区 -->
      <div v-else class="space-y-6">
        
        <!-- 模块一：⚡ 聚合动态策略组 (Dynamic Strategy Groups) -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-amber-500"></span>
              <h4 class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                聚合动态策略组 (Dynamic Strategy Groups · 共 {{ dynamicGroups.length }} 组)
              </h4>
              <span class="text-[11px] text-slate-400 font-mono hidden sm:inline">自动计算置顶于客户端 PROXY 主选择器</span>
            </div>
            <span v-if="selectedGroup" 
                  @click="selectedGroup = null" 
                  class="cursor-pointer text-xs text-sky-600 dark:text-sky-400 hover:underline flex items-center gap-1">
              <i class="fa-solid fa-xmark"></i> 清除筛选 (查看全部)
            </span>
          </div>

          <!-- 动态组卡片网格 -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            <div v-for="grp in dynamicGroups" :key="grp.name" 
                 @click="filterByGroup(grp)"
                 :class="selectedGroup && selectedGroup.name === grp.name ? 'border-sky-500 bg-sky-50/70 dark:bg-sky-950/50 ring-2 ring-sky-500/20' : 'border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-white dark:hover:bg-slate-900'"
                 class="cursor-pointer p-3.5 rounded-xl border transition flex flex-col justify-between gap-2.5 shadow-2xs group">
              <div>
                <div class="flex items-center justify-between gap-1 text-xs">
                  <span class="font-bold text-slate-900 dark:text-white truncate flex items-center gap-1.5" :title="grp.name">
                    <span>{{ grp.name }}</span>
                  </span>
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase"
                        :class="grp.type === 'fallback' ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300' : 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300'">
                    {{ grp.type }}
                  </span>
                </div>
                <div class="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                  {{ grp.strategy }}
                </div>
              </div>

              <div class="flex items-center justify-between text-[11px] pt-2 border-t border-slate-100 dark:border-slate-800/80">
                <div class="flex items-center gap-2">
                  <span class="font-mono text-slate-600 dark:text-slate-300 font-medium">
                    {{ grp.node_count }} 节点聚合
                  </span>
                  <span v-if="getGroupBestLatency(grp)" class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 flex items-center gap-0.5">
                    <i class="fa-solid fa-bolt text-[8px]"></i> {{ getGroupBestLatency(grp) }} ms
                  </span>
                </div>
                <span class="text-slate-400 dark:text-slate-500 font-mono text-[10px]">
                  {{ grp.interval }}s / {{ grp.tolerance || 50 }}ms
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 模块二：🌐 物理透传平铺节点池 (可独立折叠收起，支持单节点与批量测速) -->
        <div class="space-y-3 pt-3 border-t border-slate-100 dark:border-slate-700/60">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-sky-500"></span>
              <h4 class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                物理节点池 (Physical Nodes)
              </h4>
              <span class="text-[11px] text-slate-400 font-mono">
                共 {{ nodes.length }} 真实物理节点
              </span>
            </div>

            <div class="flex items-center gap-2 flex-wrap">
              <!-- 激活策略组高亮提示 -->
              <div v-if="selectedGroup" class="flex items-center gap-1.5 text-xs text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-950/80 px-2.5 py-1 rounded-lg border border-sky-200 dark:border-sky-800">
                <i class="fa-solid fa-filter"></i>
                <span>已过滤 <strong>{{ selectedGroup.name }}</strong> 成员 ({{ filteredNodes.length }} 个)</span>
              </div>

              <!-- 批量一键测速按钮 -->
              <button @click="pingCurrentFilteredNodes" 
                      type="button"
                      :disabled="isBatchTesting || !filteredNodes.length"
                      class="px-2.5 py-1 text-xs font-semibold rounded-lg border border-sky-300 dark:border-sky-700 bg-sky-50 dark:bg-sky-950/80 hover:bg-sky-100 dark:hover:bg-sky-900 text-sky-700 dark:text-sky-300 transition flex items-center gap-1.5 shadow-2xs disabled:opacity-50 cursor-pointer"
                      :title="'并发测试当前展示的 ' + filteredNodes.length + ' 个节点延迟'">
                <i class="fa-solid" :class="isBatchTesting ? 'fa-spinner fa-spin' : 'fa-bolt-lightning text-amber-500'"></i>
                <span>{{ isBatchTesting ? '测速中...' : '测速当前 (' + filteredNodes.length + ')' }}</span>
              </button>

              <!-- 按延迟从低到高排序切换 -->
              <button @click="sortByLatency = !sortByLatency" 
                      type="button"
                      :class="sortByLatency ? 'bg-sky-600 text-white font-bold border-sky-600' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700'"
                      class="px-2.5 py-1 text-xs font-medium rounded-lg border transition flex items-center gap-1 shadow-2xs cursor-pointer"
                      :title="sortByLatency ? '取消按延迟排序' : '按测试延迟从低到高排序'">
                <i class="fa-solid fa-arrow-down-short-wide text-[11px]"></i>
                <span>延迟排序</span>
              </button>

              <!-- 平铺节点独立折叠收起/展开按钮 -->
              <button @click="togglePhysicalCollapse" 
                      type="button"
                      class="px-2.5 py-1 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition flex items-center gap-1.5 shadow-2xs cursor-pointer">
                <i class="fa-solid text-[10px] text-sky-500" :class="isPhysicalCollapsed ? 'fa-chevron-down' : 'fa-chevron-up'"></i>
                <span>{{ isPhysicalCollapsed ? '展开平铺节点 (' + nodes.length + ')' : '折叠平铺节点' }}</span>
              </button>
            </div>
          </div>

          <!-- 平铺节点折叠状态下的简洁卡片条 -->
          <div v-if="isPhysicalCollapsed" 
               @click="togglePhysicalCollapse" 
               class="cursor-pointer p-3.5 rounded-xl border border-dashed border-slate-200 dark:border-slate-700/80 bg-slate-50/60 dark:bg-slate-900/30 hover:bg-slate-100/60 dark:hover:bg-slate-900/60 transition flex items-center justify-between">
            <div class="flex items-center gap-2.5 text-xs text-slate-500 dark:text-slate-400">
              <i class="fa-solid fa-boxes-stacked text-sky-500"></i>
              <span>物理透传节点已折叠收起（共 {{ nodes.length }} 个节点平铺在客户端 PROXY 选择器后段）。点击即可展开并支持实时测速。</span>
            </div>
            <span class="text-xs font-semibold text-sky-600 dark:text-sky-400 hover:underline flex items-center gap-1">
              展开平铺节点 ({{ nodes.length }}) <i class="fa-solid fa-chevron-down text-[10px]"></i>
            </span>
          </div>

          <!-- 平铺节点展开状态：展示搜索、国家 Pills 与网格卡片 -->
          <div v-else class="space-y-3">
            <!-- 国家地区筛选 Pills -->
            <div class="flex items-center gap-1.5 flex-wrap pt-1">
              <button @click="selectedCountry = 'ALL'" 
                      :class="selectedCountry === 'ALL' ? 'bg-sky-600 text-white font-bold' : 'bg-slate-100 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'"
                      class="px-2.5 py-1 text-xs rounded-full font-mono transition cursor-pointer">
                全部 ({{ nodes.length }})
              </button>
              <button v-for="(count, cc) in countryStats" :key="cc" 
                      @click="selectedCountry = cc"
                      :class="selectedCountry === cc ? 'bg-sky-600 text-white font-bold' : 'bg-slate-100 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'"
                      class="px-2.5 py-1 text-xs rounded-full font-mono transition flex items-center gap-1 cursor-pointer">
                <span>{{ getCountryFlag(cc) }}</span>
                <span>{{ cc }} ({{ count }})</span>
              </button>
            </div>

            <!-- 节点平铺网格 -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 pt-2">
              <div v-for="node in filteredNodes" :key="node.id"
                   class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 hover:bg-white dark:hover:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700 transition flex flex-col justify-between gap-2 shadow-2xs">
                <div>
                  <div class="flex items-center justify-between text-xs font-mono">
                    <span class="px-1.5 py-0.5 rounded font-bold uppercase text-[10px]"
                          :class="node.node_type === 'ss' ? 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300' : (node.node_type === 'vless' ? 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300')">
                      {{ node.node_type }}
                    </span>
                    <span v-if="node.is_residential" class="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 font-bold text-[10px]">
                      住宅 IP
                    </span>
                    <span class="text-slate-400 dark:text-slate-500 truncate max-w-[120px]">{{ node.source_name }}</span>
                  </div>
                  <div class="mt-2 text-xs font-semibold text-slate-900 dark:text-white line-clamp-1" :title="node.display_name">
                    {{ node.display_name }}
                  </div>
                </div>

                <!-- 底部信息行：服务器地址 + 实时测速微标签 -->
                <div class="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800/80 text-[11px] font-mono gap-1">
                  <span class="text-slate-400 dark:text-slate-500 truncate max-w-[125px]" :title="node.server + ':' + node.port">
                    {{ node.server }}:{{ node.port }}
                  </span>

                  <!-- 单节点延迟测速按钮 -->
                  <button @click.stop="pingSingleNode(node)"
                          type="button"
                          :disabled="isTestingNode(node.id)"
                          :title="isTestingNode(node.id) ? '正在测速...' : '点击测试此节点握手延迟'"
                          class="px-2 py-0.5 rounded-md text-[10px] font-bold font-mono transition flex items-center gap-1 border shadow-2xs cursor-pointer shrink-0"
                          :class="getLatencyBadgeClass(node.id)">
                    <i v-if="isTestingNode(node.id)" class="fa-solid fa-spinner fa-spin text-[9px]"></i>
                    <i v-else-if="getNodeLatency(node.id) !== null" class="fa-solid fa-bolt text-[9px]"></i>
                    <i v-else class="fa-regular fa-clock text-[9px]"></i>
                    <span>{{ formatNodeLatency(node.id) }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  `
};
