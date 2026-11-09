import { formatBytes, formatDate, maskUrl, getTrafficPercent } from '../utils/format.js';

export default {
  name: 'SourceCard',
  props: {
    source: { type: Object, required: true },
    refreshing: { type: Boolean, default: false }
  },
  emits: ['refresh', 'delete'],
  setup(props) {
    const formatRemaining = (src) => {
      if (src.remaining_text) return src.remaining_text;
      if (src.traffic_total > 0) {
        const rem = Math.max(0, src.traffic_total - (src.traffic_used || 0));
        return formatBytes(rem);
      }
      return null;
    };

    return {
      formatBytes,
      formatDate,
      maskUrl,
      getTrafficPercent,
      formatRemaining
    };
  },
  template: `
    <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 shadow-xs transition-all hover:border-slate-300 dark:hover:border-slate-700">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-bold text-slate-900 dark:text-white text-base">{{ source.name }}</span>
            <span :class="source.status === 'healthy' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/80 dark:text-emerald-300 dark:border-emerald-800' : 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/80 dark:text-rose-300 dark:border-rose-800'"
                  class="px-2 py-0.5 text-xs rounded border font-mono">
              {{ source.status === 'healthy' ? '正常' : '异常' }}
            </span>
            <span class="text-xs text-slate-500 dark:text-slate-400 font-mono bg-slate-100 dark:bg-slate-700/60 px-2 py-0.5 rounded">
              {{ source.node_count }} 节点
            </span>
          </div>
          <div class="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400 truncate" :title="source.url">
            {{ maskUrl(source.url) }}
          </div>
        </div>

        <div class="flex items-center gap-1 shrink-0">
          <button @click="$emit('refresh', source.id)" 
                  :disabled="refreshing"
                  title="刷新此源" 
                  class="p-2 text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition disabled:opacity-50">
            <i class="fa-solid fa-rotate-right text-sm" :class="{'fa-spin': refreshing}"></i>
          </button>
          <button @click="$emit('delete', source.id)" 
                  title="删除此源" 
                  class="p-2 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition">
            <i class="fa-solid fa-trash-can text-sm"></i>
          </button>
        </div>
      </div>

      <!-- 流量用量、剩余额度、账单重置与到期时间 -->
      <div class="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/60 space-y-2">
        <div class="flex items-center justify-between text-xs flex-wrap gap-2">
          <div class="flex items-center gap-1.5 font-medium text-slate-700 dark:text-slate-300">
            <i class="fa-solid fa-chart-pie text-sky-500"></i>
            <span>已用: <strong class="font-mono text-slate-900 dark:text-white">{{ formatBytes(source.traffic_used) }}</strong> ({{ getTrafficPercent(source) }}%)</span>
            <span class="text-slate-300 dark:text-slate-600">/</span>
            <span class="text-slate-500">总额: {{ formatBytes(source.traffic_total) }}</span>
            <template v-if="formatRemaining(source)">
              <span class="text-slate-300 dark:text-slate-600">|</span>
              <span class="text-emerald-600 dark:text-emerald-400 font-medium">余 {{ formatRemaining(source) }}</span>
            </template>
          </div>
          <div class="flex items-center gap-1.5 font-mono text-xs text-slate-500 dark:text-slate-400">
            <span v-if="source.reset_info" 
                  class="px-2 py-0.5 rounded bg-sky-50 text-sky-700 dark:bg-sky-950/80 dark:text-sky-300 border border-sky-200 dark:border-sky-800 text-[11px] font-sans font-medium" 
                  title="计费周期重置倒计时">
              <i class="fa-solid fa-clock-rotate-left mr-0.5"></i> {{ source.reset_info }}
            </span>
            <span>{{ source.expire_at ? formatDate(source.expire_at) : '长期有效' }}</span>
          </div>
        </div>

        <!-- 视觉进度条 -->
        <div v-if="source.traffic_total > 0" class="w-full h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden flex" title="已用流量比例">
          <div class="h-full bg-gradient-to-r from-sky-500 to-blue-600 rounded-full transition-all duration-300"
               :style="{ width: Math.min(100, Math.max(getTrafficPercent(source), source.traffic_used > 0 ? 2 : 0)) + '%' }"></div>
        </div>
      </div>
    </div>
  `
};
