import { ref, computed } from 'vue';

export default {
  name: 'NodePool',
  props: {
    nodes: { type: Array, required: true },
    dynamicGroups: { type: Array, default: () => [] }
  },
  setup(props) {
    const isCollapsed = ref(localStorage.getItem('sub_egress_nodepool_collapsed') === 'true');
    const searchQuery = ref('');
    const selectedCountry = ref('ALL');
    const selectedGroup = ref(null);

    const toggleCollapse = () => {
      isCollapsed.value = !isCollapsed.value;
      localStorage.setItem('sub_egress_nodepool_collapsed', isCollapsed.value ? 'true' : 'false');
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
      }
    };

    const filteredNodes = computed(() => {
      return props.nodes.filter(n => {
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
    });

    return {
      isCollapsed,
      toggleCollapse,
      searchQuery,
      selectedCountry,
      selectedGroup,
      filterByGroup,
      countryStats,
      getCountryFlag,
      filteredNodes
    };
  },
  template: `
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 shadow-xs space-y-5">
      <!-- 顶部头部：标题、统计与折叠切换按钮 -->
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
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">聚合动态策略组自动测速容灾 + 物理透传平铺，客户端自由选择</p>
          </div>
        </div>

        <!-- 右侧操作区：折叠收起/展开按钮 -->
        <div class="flex items-center gap-2">
          <!-- 搜索框（展开时展示） -->
          <div v-show="!isCollapsed" class="relative">
            <i class="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-xs text-slate-400"></i>
            <input v-model="searchQuery" type="text" placeholder="搜索节点名/地区/协议..." 
                   class="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-sky-500 w-44">
          </div>

          <!-- 折叠 / 展开主按钮 -->
          <button @click="toggleCollapse" 
                  class="px-3.5 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 transition flex items-center gap-1.5 shadow-2xs"
                  :title="isCollapsed ? '展开查看节点大盘与动态组' : '折叠大盘节省空间'">
            <i class="fa-solid text-xs text-sky-500" :class="isCollapsed ? 'fa-chevron-down' : 'fa-chevron-up'"></i>
            <span>{{ isCollapsed ? '展开大盘' : '折叠收起' }}</span>
          </button>
        </div>
      </div>

      <!-- 折叠状态下的轻量级概览条 -->
      <div v-if="isCollapsed" 
           @click="toggleCollapse" 
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
            <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">包含日区/美区/港区/家宽/全局动态容灾组，点击此处随时展开查看</p>
          </div>
        </div>
        <span class="text-xs font-semibold text-sky-600 dark:text-sky-400 flex items-center gap-1 hover:underline">
          展开大盘 <i class="fa-solid fa-chevron-down text-[10px]"></i>
        </span>
      </div>

      <!-- 展开状态下的完整大盘内容 -->
      <div v-else class="space-y-6">
        
        <!-- 模块一：⚡ 聚合动态策略组 (Dynamic Strategy Groups) -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-amber-500"></span>
              <h4 class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                聚合动态策略组 (Dynamic Strategy Groups)
              </h4>
              <span class="text-[11px] text-slate-400 font-mono">自动计算生成的智能选点组，置顶于客户端主选择器</span>
            </div>
            <span v-if="selectedGroup" 
                  @click="selectedGroup = null" 
                  class="cursor-pointer text-xs text-sky-600 dark:text-sky-400 hover:underline flex items-center gap-1">
              <i class="fa-solid fa-xmark"></i> 清除策略组筛选 (显示全部)
            </span>
          </div>

          <!-- 动态组卡片网格 -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            <div v-for="grp in dynamicGroups" :key="grp.name" 
                 @click="filterByGroup(grp)"
                 :class="selectedGroup && selectedGroup.name === grp.name ? 'border-sky-500 bg-sky-50/60 dark:bg-sky-950/40 ring-2 ring-sky-500/20' : 'border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-white dark:hover:bg-slate-900'"
                 class="cursor-pointer p-3.5 rounded-xl border transition flex flex-col justify-between gap-2.5 shadow-2xs group">
              <div>
                <div class="flex items-center justify-between gap-1 text-xs">
                  <span class="font-bold text-slate-900 dark:text-white truncate flex items-center gap-1.5" :title="grp.name">
                    <span>{{ grp.country_flag }}</span>
                    <span>{{ grp.name.replace(/\\[动态·[^\\]]+\\]\\s*/, '') }}</span>
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
                <span class="font-mono text-slate-600 dark:text-slate-300 font-medium">
                  {{ grp.node_count }} 节点聚合
                </span>
                <span class="text-slate-400 dark:text-slate-500 font-mono text-[10px]">
                  {{ grp.interval }}s / {{ grp.tolerance || 50 }}ms
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 模块二：🌐 物理透传平铺节点池 (Physical Pass-Through Nodes) -->
        <div class="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-700/60">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-sky-500"></span>
              <h4 class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                平铺物理透传节点池 (Physical Pass-Through Nodes)
              </h4>
              <span class="text-[11px] text-slate-400 font-mono">
                当前筛选: {{ filteredNodes.length }} / {{ nodes.length }} 节点
              </span>
            </div>

            <!-- 激活策略组高亮提示 -->
            <div v-if="selectedGroup" class="flex items-center gap-1.5 text-xs text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-950/80 px-2.5 py-1 rounded-lg border border-sky-200 dark:border-sky-800">
              <i class="fa-solid fa-filter"></i>
              <span>正在过滤属于 <strong>{{ selectedGroup.name }}</strong> 的成员节点</span>
            </div>
          </div>

          <!-- 国家地区筛选 Pills -->
          <div class="flex items-center gap-1.5 flex-wrap pt-1">
            <button @click="selectedCountry = 'ALL'" 
                    :class="selectedCountry === 'ALL' ? 'bg-sky-600 text-white font-bold' : 'bg-slate-100 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'"
                    class="px-2.5 py-1 text-xs rounded-full font-mono transition">
              全部 ({{ nodes.length }})
            </button>
            <button v-for="(count, cc) in countryStats" :key="cc" 
                    @click="selectedCountry = cc"
                    :class="selectedCountry === cc ? 'bg-sky-600 text-white font-bold' : 'bg-slate-100 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'"
                    class="px-2.5 py-1 text-xs rounded-full font-mono transition flex items-center gap-1">
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
              <div class="text-[11px] font-mono text-slate-400 dark:text-slate-500 truncate">
                {{ node.server }}:{{ node.port }}
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  `
};
