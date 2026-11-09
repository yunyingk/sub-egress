import SourceCard from './SourceCard.js';

export default {
  name: 'SourceList',
  components: {
    SourceCard
  },
  props: {
    sources: { type: Array, required: true },
    refreshingIds: { type: Array, default: () => [] }
  },
  emits: ['openAddModal', 'refreshSource', 'deleteSource'],
  template: `
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-sky-500"></span>
          上游数据源 (Inbound Sources)
          <span class="text-xs font-normal text-slate-500 dark:text-slate-400">({{ sources.length }} 家已接入)</span>
        </h2>
        <button @click="$emit('openAddModal')" 
                class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-sky-50 text-sky-700 hover:bg-sky-100 dark:bg-sky-950/60 dark:text-sky-300 dark:hover:bg-sky-900/60 border border-sky-200 dark:border-sky-800 transition flex items-center gap-1.5 shadow-xs">
          <i class="fa-solid fa-plus text-xs"></i> 添加新源
        </button>
      </div>

      <!-- 源卡片列表 -->
      <div class="space-y-3">
        <div v-if="sources.length === 0" class="p-8 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 text-center text-slate-400 text-sm">
          暂无接入的上游源，请点击上方「添加新源」添加
        </div>
        <SourceCard 
          v-for="src in sources" 
          :key="src.id" 
          :source="src" 
          :refreshing="refreshingIds.includes(src.id)"
          @refresh="$emit('refreshSource', $event)"
          @delete="$emit('deleteSource', $event)"
        />
      </div>
    </div>
  `
};
