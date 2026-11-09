import { ref, computed } from 'vue';

export default {
  name: 'NodePool',
  props: {
    nodes: { type: Array, required: true }
  },
  setup(props) {
    const searchQuery = ref('');
    const selectedCountry = ref('ALL');

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

    const filteredNodes = computed(() => {
      return props.nodes.filter(n => {
        if (selectedCountry.value !== 'ALL' && n.country_code !== selectedCountry.value) {
          return false;
        }
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
      searchQuery,
      selectedCountry,
      countryStats,
      getCountryFlag,
      filteredNodes
    };
  },
  template: `
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 shadow-xs space-y-4">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-lg bg-slate-100 dark:bg-slate-700/60 flex items-center justify-center text-slate-700 dark:text-slate-300 font-bold">
            <i class="fa-solid fa-network-wired text-sky-500"></i>
          </div>
          <div>
            <h3 class="text-base font-bold text-slate-900 dark:text-white">合并节点池大盘 (Active Node Pool)</h3>
            <p class="text-xs text-slate-500 dark:text-slate-400">已接入并平铺的可用物理透传节点，支持即时搜索与地区筛选</p>
          </div>
        </div>

        <!-- 节点过滤器 -->
        <div class="flex items-center gap-2">
          <div class="relative">
            <i class="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-xs text-slate-400"></i>
            <input v-model="searchQuery" type="text" placeholder="搜索节点名/地区/协议..." 
                   class="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-sky-500 w-48">
          </div>
          <span class="text-xs font-mono px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
            共 {{ filteredNodes.length }} / {{ nodes.length }} 节点
          </span>
        </div>
      </div>

      <!-- 国家地区筛选 Pills -->
      <div class="flex items-center gap-1.5 flex-wrap pt-2">
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
             class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 hover:bg-white dark:hover:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700 transition flex flex-col justify-between gap-2 shadow-xs">
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
  `
};
