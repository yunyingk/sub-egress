<template>
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

          <!-- 操作按钮组 (复制链接 / 悬浮扫码二维码 / 新标签页预览) -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1 relative">
            <!-- 1. 复制链接 -->
            <button @click="copySubscriptionUrl" class="px-3 py-2 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition flex items-center justify-center gap-1.5 shadow-xs shadow-sky-600/20">
              <i class="fa-solid" :class="copied ? 'fa-check text-emerald-300' : 'fa-copy'"></i>
              <span>{{ copied ? '已成功复制!' : '复制订阅链接' }}</span>
            </button>

            <!-- 2. 二维码扫码 (带悬浮/点击展示) -->
            <div class="relative" @mouseenter="onMouseEnterQr" @mouseleave="onMouseLeaveQr">
              <button @click="toggleQr" 
                      :class="showQr ? 'bg-sky-50 dark:bg-sky-950/60 border-sky-400 text-sky-600 dark:text-sky-300' : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700'"
                      class="w-full px-3 py-2 text-xs font-semibold rounded-lg border transition flex items-center justify-center gap-1.5 shadow-xs">
                <i class="fa-solid fa-qrcode text-sky-500 text-sm"></i>
                <span>二维码扫码</span>
              </button>

              <!-- 二维码浮层卡片 -->
              <div v-show="showQr" 
                   class="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 w-72 p-4 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 z-30 transition-all">
                <div class="flex items-center justify-between pb-2 mb-3 border-b border-slate-100 dark:border-slate-700 text-xs font-bold text-slate-800 dark:text-slate-200">
                  <span class="flex items-center gap-1.5">
                    <i class="fa-solid fa-mobile-screen text-sky-500"></i>
                    移动设备扫码导入
                  </span>
                  <button @click.stop="showQr = false" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                    <i class="fa-solid fa-xmark"></i>
                  </button>
                </div>

                <!-- 二维码容器 (白色衬底保证高对比度扫码) -->
                <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-inner flex items-center justify-center mx-auto w-[196px] h-[196px]">
                  <div id="qrcode-container-box" class="flex items-center justify-center"></div>
                </div>

                <div class="mt-3 text-center space-y-1.5">
                  <p class="text-[11px] text-slate-500 dark:text-slate-400">
                    手机相机扫码即可导入客户端
                  </p>
                  <div class="pt-1 flex items-center justify-center gap-2">
                    <a :href="clashSchemeUrl" class="px-2.5 py-1 text-[11px] font-semibold rounded-md bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-300 border border-sky-200 dark:border-sky-800 hover:bg-sky-100 transition">
                      Clash 一键导入
                    </a>
                    <a :href="singboxSchemeUrl" class="px-2.5 py-1 text-[11px] font-semibold rounded-md bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 hover:bg-emerald-100 transition">
                      Sing-box 导入
                    </a>
                  </div>
                </div>
              </div>
            </div>

            <!-- 3. 新标签页打开 -->
            <a :href="activeSubscriptionUrl" target="_blank" class="px-3 py-2 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition flex items-center justify-center gap-1.5 shadow-xs">
              <i class="fa-solid fa-arrow-up-right-from-square"></i>
              <span>新标签页预览</span>
            </a>
          </div>
        </div>

        <!-- 状态提示 -->
        <div class="p-3 rounded-lg bg-sky-50/70 dark:bg-sky-950/40 border border-sky-100 dark:border-sky-900/60 text-xs text-sky-900 dark:text-sky-300 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-shield-halved text-sky-600 dark:text-sky-400"></i>
            <span>安全令牌: <span class="font-mono font-bold">{{ settings.sub_hash_token ? settings.sub_hash_token.substring(0, 8) + '...' : '未启用' }}</span></span>
          </div>
          <div class="flex items-center gap-3">
            <button type="button" @click="resetSubscriptionToken" :disabled="resettingToken" class="text-xs font-semibold text-sky-600 dark:text-sky-400 hover:underline disabled:opacity-50">
              {{ resettingToken ? '重置中…' : '重置订阅链接' }}
            </button>
            <button @click="$emit('openSettings')" class="text-xs font-semibold text-sky-600 dark:text-sky-400 hover:underline">
              设置分流规则 →
            </button>
          </div>
        </div>
        <p v-if="tokenResetMessage" role="status" class="text-xs" :class="tokenResetError ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'">{{ tokenResetMessage }}</p>

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
  
</template>

<script>
import { ref, computed, watch, nextTick } from 'vue';

export default {
  name: 'OutboundFeed',
  props: {
    settings: { type: Object, required: true },
    selectedTarget: { type: String, default: 'clash' }
  },
  emits: ['update:selectedTarget', 'openSettings', 'tokenReset'],
  setup(props, { emit }) {
    const copied = ref(false);
    const showQr = ref(false);
    const resettingToken = ref(false);
    const tokenResetMessage = ref('');
    const tokenResetError = ref(false);

    const resetSubscriptionToken = async () => {
      if (resettingToken.value || !window.confirm('重置后旧订阅链接将失效，需要在所有客户端更新链接。确定重置吗？')) return;
      resettingToken.value = true;
      tokenResetMessage.value = '';
      try {
        const res = await fetch('/api/user/regenerate-token', { method: 'POST' });
        if (!res.ok) throw new Error('reset failed');
        const data = await res.json();
        if (typeof data.new_token !== 'string' || !data.new_token) throw new Error('invalid response');
        emit('tokenReset', data.new_token);
        tokenResetError.value = false;
        tokenResetMessage.value = '订阅链接已重置，请复制新链接并更新客户端。';
      } catch (e) {
        tokenResetError.value = true;
        tokenResetMessage.value = '重置结果未确认，请刷新页面查看当前链接后再重试。';
      } finally {
        resettingToken.value = false;
      }
    };
    let hoverTimeout = null;
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

    const clashSchemeUrl = computed(() => {
      return `clash://install-config?url=${encodeURIComponent(activeSubscriptionUrl.value)}&name=${encodeURIComponent(customName.value || defaultPlaceholder.value)}`;
    });

    const singboxSchemeUrl = computed(() => {
      return `sing-box://import-remote-profile?url=${encodeURIComponent(activeSubscriptionUrl.value)}#${encodeURIComponent(customName.value || defaultPlaceholder.value)}`;
    });

    const renderQrCode = () => {
      nextTick(() => {
        const container = document.getElementById('qrcode-container-box');
        if (!container) return;
        container.innerHTML = '';
        if (window.QRCode) {
          new window.QRCode(container, {
            text: activeSubscriptionUrl.value,
            width: 170,
            height: 170,
            colorDark: "#0f172a",
            colorLight: "#ffffff",
            correctLevel: window.QRCode.CorrectLevel.M
          });
        }
      });
    };

    const toggleQr = () => {
      showQr.value = !showQr.value;
      if (showQr.value) renderQrCode();
    };

    const onMouseEnterQr = () => {
      clearTimeout(hoverTimeout);
      showQr.value = true;
      renderQrCode();
    };

    const onMouseLeaveQr = () => {
      hoverTimeout = setTimeout(() => {
        showQr.value = false;
      }, 300);
    };

    watch(activeSubscriptionUrl, () => {
      if (showQr.value) renderQrCode();
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
      showQr,
      resettingToken,
      tokenResetMessage,
      tokenResetError,
      resetSubscriptionToken,
      customName,
      onNameChange,
      defaultPlaceholder,
      activeSubscriptionUrl,
      formatExt,
      clashSchemeUrl,
      singboxSchemeUrl,
      toggleQr,
      onMouseEnterQr,
      onMouseLeaveQr,
      copySubscriptionUrl,
      setTarget
    };
  }
};
</script>
