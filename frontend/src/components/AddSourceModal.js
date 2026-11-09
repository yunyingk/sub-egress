import { ref } from 'vue';

export default {
  name: 'AddSourceModal',
  props: {
    visible: { type: Boolean, default: false },
    creating: { type: Boolean, default: false }
  },
  emits: ['close', 'create'],
  setup(props, { emit }) {
    const form = ref({ name: '', url: '' });

    const handleCreate = () => {
      if (!form.value.name.trim() || !form.value.url.trim()) return;
      emit('create', { name: form.value.name.trim(), url: form.value.url.trim() });
      form.value = { name: '', url: '' };
    };

    return {
      form,
      handleCreate
    };
  },
  template: `
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div class="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl max-w-md w-full p-6 space-y-5">
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-700 pb-3">
          <h3 class="font-bold text-base text-slate-900 dark:text-white">添加上游数据源</h3>
          <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <i class="fa-solid fa-xmark text-lg"></i>
          </button>
        </div>

        <div class="space-y-3">
          <div>
            <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">源名称 (备注)</label>
            <input v-model="form.name" type="text" placeholder="例如: 机场A / 自建专线" 
                   class="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">订阅链接 / 协议 URL</label>
            <input v-model="form.url" type="text" placeholder="https://... 或 ss://..." 
                   class="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-700">
          <button @click="$emit('close')" class="px-4 py-2 text-xs font-medium rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition">
            取消
          </button>
          <button @click="handleCreate" :disabled="creating || !form.name || !form.url" 
                  class="px-4 py-2 text-xs font-bold rounded-lg bg-sky-600 hover:bg-sky-500 text-white shadow-xs transition flex items-center gap-1.5 disabled:opacity-50">
            <i class="fa-solid fa-plus" :class="{'fa-spin': creating}"></i>
            <span>{{ creating ? '添加并同步中...' : '确认添加' }}</span>
          </button>
        </div>
      </div>
    </div>
  `
};
