<template>
    <div :class="{'opacity-65 saturate-60': source.is_shared && source.is_enabled_for_user === false}"
         class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 shadow-xs transition-all hover:border-slate-300 dark:hover:border-slate-700">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-bold text-slate-900 dark:text-white text-base">{{ source.name }}</span>
            <span v-if="source.is_shared" 
                  class="px-2 py-0.5 text-xs rounded bg-purple-50 text-purple-700 dark:bg-purple-950/80 dark:text-purple-300 border border-purple-200 dark:border-purple-800 font-mono font-medium flex items-center gap-1">
              <i class="fa-solid fa-globe text-[10px]"></i> 平台共享
            </span>
            <span v-if="source.is_shared && source.is_enabled_for_user === false"
                  class="px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 border border-slate-200 dark:border-slate-700 font-mono font-medium">
              本人已停用
            </span>
            <span :class="source.status === 'healthy' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/80 dark:text-emerald-300 dark:border-emerald-800' : 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/80 dark:text-rose-300 dark:border-rose-800'"
                  class="px-2 py-0.5 text-xs rounded border font-mono">
              {{ source.status === 'healthy' ? '正常' : '异常' }}
            </span>
            <span class="text-xs text-slate-500 dark:text-slate-400 font-mono bg-slate-100 dark:bg-slate-700/60 px-2 py-0.5 rounded">
              {{ source.node_count }} 节点
            </span>
          </div>
          <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">所有者：{{ source.owner_username }} · 创建人：{{ source.creator_username || '未知' }}</div>
          <div class="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400 truncate" :title="source.url">
            {{ maskUrl(source.url) }}
          </div>
        </div>

        <div class="flex items-center gap-2 shrink-0">
          <!-- 平台共享源：显示个人专属启用/停用切换开关，杜绝删除与全局刷新按钮 -->
          <template v-if="source.is_shared">
            <button @click="$emit('toggleShared', source.id)" 
                    type="button"
                    :class="source.is_enabled_for_user !== false ? 'bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800' : 'bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'"
                    class="px-2.5 py-1 text-xs font-medium rounded-lg border transition flex items-center gap-1.5 cursor-pointer shadow-2xs"
                    :title="source.is_enabled_for_user !== false ? '点击在我的订阅中停用此平台共享源' : '点击在我的订阅中启用此平台共享源'">
              <i class="fa-solid" :class="source.is_enabled_for_user !== false ? 'fa-toggle-on text-purple-600 dark:text-purple-400 text-sm' : 'fa-toggle-off text-slate-400 text-sm'"></i>
              <span>{{ source.is_enabled_for_user !== false ? '已启用 (仅本人)' : '已停用 (仅本人)' }}</span>
            </button>
            <div title="平台公共基础设施源：仅管理员可在管理控制台中全局维护" 
                 class="p-1.5 text-slate-300 dark:text-slate-600 cursor-help">
              <i class="fa-solid fa-shield-halved text-xs"></i>
            </div>
          </template>

          <!-- 个人私有源：提供专属刷新与删除按钮 -->
          <template v-else>
            <button @click="$emit('refresh', source.id)" 
                    :disabled="refreshing"
                    title="刷新此私有源" 
                    class="p-2 text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition disabled:opacity-50 cursor-pointer">
              <i class="fa-solid fa-rotate-right text-sm" :class="{'fa-spin': refreshing}"></i>
            </button>
            <button @click="$emit('delete', source.id)" 
                    title="删除此个人私有源" 
                    class="p-2 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition cursor-pointer">
              <i class="fa-solid fa-trash-can text-sm"></i>
            </button>
          </template>
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
  
</template>

<script>
import { formatBytes, formatDate, maskUrl, getTrafficPercent } from '../utils/format.js';

export default {
  name: 'SourceCard',
  props: {
    source: { type: Object, required: true },
    refreshing: { type: Boolean, default: false }
  },
  emits: ['refresh', 'delete', 'toggleShared'],
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
  }
};
</script>
