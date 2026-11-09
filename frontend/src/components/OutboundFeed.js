import { ref, computed } from 'vue';

export default {
  name: 'OutboundFeed',
  props: {
    settings: { type: Object, required: true },
    selectedTarget: { type: String, default: 'clash' }
  },
  emits: ['update:selectedTarget', 'openSettings'],
  setup(props, { emit }) {
    const copied = ref(false);
    const customName = ref(localStorage.getItem('sub_egress_custom_name') || '');

    const onNameChange = () => {
      if (customName.value && customName.value.trim()) {
        localStorage.setItem('sub_egress_custom_name', customName.value.trim());
      } else {
        localStorage.removeItem('sub_egress_custom_name');
      }
    };

    const defaultPlaceholder = computed(() => {
      return props.settings.subscription_title || 'sub-egress';
    });

    const activeSubscriptionUrl = computed(() => {
      const origin = window.location.origin;
      const token = props.settings.sub_hash_token;
      const target = props.selectedTarget;
      const params = new URLSearchParams();
      params.append('target', target);
      if (customName.value && customName.value.trim()) {
        params.append('name', customName.value.trim());
      }
      const queryStr = params.toString();
      if (token) {
        return `${origin}/c/${token}?${queryStr}`;
      }
      return `${origin}/feed?${queryStr}`;
    });

    const formatExt = computed(() => {
      if (props.selectedTarget === 'sing-box') return 'JSON (Sing-box)';
      if (props.selectedTarget === 'base64') return 'TXT (Base64)';
      return 'YAML (Mihomo)';
    });

    const copySubscriptionUrl = () => {
      navigator.clipboard.writeText(activeSubscriptionUrl.value);
      copied.value = true;
      setTimeout(() => { copied.value = false; }, 2500);
    };

    const setTarget = (t) => {
      emit('update:selectedTarget', t);
    };

    return {
      copied,
      customName,
      onNameChange,
      defaultPlaceholder,
      activeSubscriptionUrl,
      formatExt,
      copySubscriptionUrl,
      setTarget
    };
  },
  template: `
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
          下游分发中心 (Outbound Feeds)
        </h2>
        <span class="px-2.5 py-1 text-xs rounded-full font-mono font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800">
          全量合流 · 二元选择
        </span>
      </div>

      <div class="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 shadow-xs space-y-5">
        
        <!-- 目标内核选择标签页 -->
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
            目标客户端内核 (Target Type)
          </label>
          <div class="grid grid-cols-3 gap-2 p-1 bg-slate-100 dark:bg-slate-900/80 rounded-xl border border-slate-200 dark:border-slate-700/70">
            <button @click="setTarget('clash')" 
                    :class="selectedTarget === 'clash' ? 'bg-white dark:bg-slate-800 text-sky-600 dark:text-sky-400 shadow-xs font-bold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white font-medium'"
                    class="py-2 text-xs rounded-lg transition-all flex items-center justify-center gap-1.5">
              <i class="fa-solid fa-bolt"></i> Clash / Mihomo
            </button>
            <button @click="setTarget('sing-box')" 
                    :class="selectedTarget === 'sing-box' ? 'bg-white dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 shadow-xs font-bold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white font-medium'"
                    class="py-2 text-xs rounded-lg transition-all flex items-center justify-center gap-1.5">
              <i class="fa-solid fa-cube"></i> Sing-box
            </button>
            <button @click="setTarget('base64')" 
                    :class="selectedTarget === 'base64' ? 'bg-white dark:bg-slate-800 text-purple-600 dark:text-purple-400 shadow-xs font-bold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white font-medium'"
                    class="py-2 text-xs rounded-lg transition-all flex items-center justify-center gap-1.5">
              <i class="fa-solid fa-list-ul"></i> Base64 / URI
            </button>
          </div>
        </div>

        <!-- 自定义订阅卡片名称 (Profile Name) -->
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              客户端卡片名称 (Profile Name · 动态调节)
            </label>
            <span v-if="customName" @click="customName = ''; onNameChange()" class="cursor-pointer text-[11px] text-slate-400 hover:text-sky-500 flex items-center gap-1">
              <i class="fa-solid fa-arrow-rotate-left"></i> 恢复默认
            </span>
          </div>
          <div class="relative">
            <i class="fa-solid fa-tag absolute left-3 top-2.5 text-xs text-slate-400"></i>
            <input v-model="customName" @input="onNameChange" type="text" 
                   :placeholder="defaultPlaceholder"
                   class="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 font-medium">
          </div>
          <p class="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            导入 Clash Verge / Mihomo 时将直接以此纯文本命名卡片（无任何 .yaml 文件后缀）。
          </p>
        </div>

        <!-- 订阅链接展示区 -->
        <div class="space-y-2">
          <div class="flex items-center justify-between text-xs">
            <span class="font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
              <i class="fa-solid fa-link text-sky-500"></i> 生成的专属订阅端点
            </span>
            <span class="font-mono text-slate-500 dark:text-slate-400">
              格式: <span class="font-bold uppercase text-sky-600 dark:text-sky-400">{{ formatExt }}</span>
            </span>
          </div>

          <!-- 完整的哈希订阅 URL 容器 -->
          <div class="p-3 bg-slate-50 dark:bg-slate-900/90 rounded-lg border border-slate-200 dark:border-slate-700/80 font-mono text-xs text-slate-800 dark:text-slate-200 break-all select-all flex items-center justify-between gap-2 shadow-inner">
            <span class="overflow-x-auto py-1">{{ activeSubscriptionUrl }}</span>
          </div>

          <!-- 操作按钮组 -->
          <div class="grid grid-cols-2 gap-2 pt-1">
            <button @click="copySubscriptionUrl" class="px-4 py-2 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition flex items-center justify-center gap-2 shadow-xs shadow-sky-600/20">
              <i class="fa-solid" :class="copied ? 'fa-check text-emerald-300' : 'fa-copy'"></i>
              <span>{{ copied ? '已成功复制!' : '复制订阅链接' }}</span>
            </button>

            <a :href="activeSubscriptionUrl" target="_blank" class="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition flex items-center justify-center gap-2 shadow-xs">
              <i class="fa-solid fa-arrow-up-right-from-square"></i>
              <span>在新标签页预览</span>
            </a>
          </div>
        </div>

        <!-- 状态提示 -->
        <div class="p-3 rounded-lg bg-sky-50/70 dark:bg-sky-950/40 border border-sky-100 dark:border-sky-900/60 text-xs text-sky-900 dark:text-sky-300 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-shield-halved text-sky-600 dark:text-sky-400"></i>
            <span>安全令牌: <span class="font-mono font-bold">{{ settings.sub_hash_token ? settings.sub_hash_token.substring(0, 8) + '...' : '未启用' }}</span></span>
          </div>
          <button @click="$emit('openSettings')" class="text-xs font-semibold text-sky-600 dark:text-sky-400 hover:underline">
            设置令牌 →
          </button>
        </div>

        <!-- 规范说明 -->
        <div class="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400 space-y-2">
          <div class="font-bold text-slate-900 dark:text-slate-200 flex items-center gap-1.5">
            <i class="fa-solid fa-circle-check text-emerald-500"></i> 极简二元制单一节点选择原则：
          </div>
          <ul class="space-y-1.5 pl-4 list-disc text-slate-500 dark:text-slate-400">
            <li><strong class="text-slate-700 dark:text-slate-300">双门双出站</strong>：主门 [7897] 主出站（TUN/全局，默认美国家宽），副门 [7898] 副出站（终端高速，默认日区低延迟）。</li>
            <li><strong class="text-slate-700 dark:text-slate-300">供应商专区</strong>：按 [RE] 住宅专区、[SD] 机场专区整组调用，随时全局切换供应商。</li>
            <li><strong class="text-slate-700 dark:text-slate-300">地区智能组</strong>：港区、日区、台区、狮城等同国同区自动测速优选，绝不跨区乱跳。</li>
            <li><strong class="text-slate-700 dark:text-slate-300">物理节点池</strong>：精简命名，单机直点，由客户端自由固定指定。</li>
          </ul>
        </div>
      </div>
    </div>
  `
};
