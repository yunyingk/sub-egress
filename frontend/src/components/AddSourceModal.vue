<template>
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div class="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl max-w-md w-full p-6 space-y-5">
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-700 pb-3">
          <h3 class="font-bold text-base text-slate-900 dark:text-white flex items-center gap-2">
            <i class="fa-solid fa-lock text-sky-500"></i>
            <span>添加个人专属节点源</span>
          </h3>
          <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer">
            <i class="fa-solid fa-xmark text-lg"></i>
          </button>
        </div>

        <!-- 专属私有提示卡片 -->
        <div class="p-3 rounded-xl bg-sky-50 dark:bg-sky-950/40 border border-sky-100 dark:border-sky-900/60 text-[11px] text-sky-800 dark:text-sky-300 flex items-start gap-2">
          <i class="fa-solid fa-shield-halved text-sky-500 mt-0.5 shrink-0"></i>
          <span>此数据源为<strong>个人专属私有</strong>，仅绑定至您的当前账号与个人订阅中，绝不对其他租户公开或共享。若需配置全站公共源，请在管理员控制台配置。</span>
        </div>

        <div class="space-y-3">
          <!-- 订阅 URL 优先录入，自动触发探测 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1 flex items-center justify-between">
              <span>订阅链接 / 节点协议 URL</span>
              <span v-if="isProbing" class="text-sky-600 dark:text-sky-400 text-[10px] font-normal flex items-center gap-1">
                <i class="fa-solid fa-spinner fa-spin"></i> 正在智能探测名称与节点...
              </span>
            </label>
            <input v-model="form.url" 
                   @blur="triggerProbe"
                   type="text" 
                   placeholder="https://... 或 ss://... (粘贴后自动识别名称)" 
                   class="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
            
            <!-- 探测成功反馈提示 -->
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
            <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
              源名称 (备注)
              <span class="text-[10px] font-normal text-slate-400">(填入链接后自动填入，亦可手动修改)</span>
            </label>
            <input v-model="form.name" type="text" placeholder="例如: 机场A / 自建专线" 
                   class="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-700">
          <button @click="$emit('close')" class="px-4 py-2 text-xs font-medium rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition">
            取消
          </button>
          <button @click="handleCreate" :disabled="creating || !form.name || !form.url" 
                  class="px-4 py-2 text-xs font-bold rounded-lg bg-sky-600 hover:bg-sky-500 text-white shadow-xs transition flex items-center gap-1.5 disabled:opacity-50 cursor-pointer">
            <i class="fa-solid fa-plus" :class="{'fa-spin': creating}"></i>
            <span>{{ creating ? '添加并同步中...' : '确认添加' }}</span>
          </button>
        </div>
      </div>
    </div>
  
</template>

<script>
import { ref, watch } from 'vue';

export default {
  name: 'AddSourceModal',
  props: {
    visible: { type: Boolean, default: false },
    creating: { type: Boolean, default: false }
  },
  emits: ['close', 'create'],
  setup(props, { emit }) {
    const form = ref({ name: '', url: '' });
    const isProbing = ref(false);
    const probeInfo = ref(null);
    let probeTimer = null;
    let autoFilledName = '';

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
            // 若用户未手工填写名称，或者当前名称就是此前自动填入的，则自动更新为最新识别出的名称
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

    // 监听 URL 输入，debounce 500ms 自动触发智能探测
    watch(() => form.value.url, (newVal) => {
      if (probeTimer) clearTimeout(probeTimer);
      if (!newVal || newVal.trim().length < 10) {
        probeInfo.value = null;
        return;
      }
      probeTimer = setTimeout(() => {
        triggerProbe();
      }, 500);
    });

    const handleCreate = () => {
      if (!form.value.name.trim() || !form.value.url.trim()) return;
      emit('create', { name: form.value.name.trim(), url: form.value.url.trim() });
      form.value = { name: '', url: '' };
      probeInfo.value = null;
      autoFilledName = '';
    };

    return {
      form,
      isProbing,
      probeInfo,
      triggerProbe,
      handleCreate
    };
  }
};
</script>
