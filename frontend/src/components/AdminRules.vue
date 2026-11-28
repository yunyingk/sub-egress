<template>
  <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 w-full p-6 md:p-8 flex flex-col space-y-6">
    <!-- 头部说明与刷新按钮 -->
    <div class="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-700 shrink-0">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 flex items-center justify-center">
          <i class="fa-solid fa-sliders text-lg"></i>
        </div>
        <div>
          <h3 class="text-lg font-bold text-slate-900 dark:text-white">系统全局规则与订阅设置</h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">配置平台级权威分流策略与全局默认订阅参数，优先级高于所有用户规则</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button @click="load" :disabled="loading" 
                class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
          <i class="fa-solid fa-arrows-rotate" :class="{'fa-spin': loading}"></i>刷新
        </button>
      </div>
    </div>

    <!-- 提示消息栏 -->
    <div v-if="message" class="p-3.5 rounded-xl border text-xs flex items-center justify-between gap-2 shrink-0 transition-all"
         :class="error ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300' : 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'">
      <div class="flex items-center gap-2">
        <i class="fa-solid" :class="error ? 'fa-circle-exclamation text-rose-500' : 'fa-circle-check text-emerald-500'"></i>
        <span>{{ message }}</span>
      </div>
      <button @click="message = ''" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 cursor-pointer">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>

    <!-- 模块 1: 全局订阅设置 -->
    <div class="p-5 rounded-xl bg-slate-50/70 dark:bg-slate-750/50 border border-slate-200 dark:border-slate-700 space-y-4">
      <div class="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-slate-200">
        <i class="fa-solid fa-gear text-purple-500"></i>
        <span>全局订阅默认设置</span>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- 默认客户端内核 -->
        <div>
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">默认客户端内核</label>
          <select v-model="settings.default_target" 
                  class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500">
            <option value="clash">Clash / Mihomo</option>
            <option value="sing-box">sing-box</option>
            <option value="base64">Base64</option>
          </select>
          <p class="text-[10px] text-slate-400 mt-1">未指定 target 参数时的默认格式</p>
        </div>

        <!-- 更新间隔 -->
        <div>
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">更新间隔 (小时)</label>
          <input v-model.number="settings.update_interval" type="number" min="1" max="72" 
                 class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500">
          <p class="text-[10px] text-slate-400 mt-1">客户端订阅推荐刷新周期 (1~72h)</p>
        </div>

        <!-- 访问安全要求 (固定强制鉴权) -->
        <div>
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">访问安全要求</label>
          <div class="flex items-center gap-2 px-3 py-2 text-xs rounded-xl border border-emerald-200 dark:border-emerald-800/60 bg-emerald-50/70 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 h-[34px]">
            <i class="fa-solid fa-shield-halved shrink-0"></i>
            <span class="font-medium truncate">已强制启用专属令牌鉴权</span>
          </div>
          <p class="text-[10px] text-slate-400 mt-1">所有订阅请求必须携带合法用户令牌，/feed 匿名入口已停用</p>
        </div>

        <!-- 写入 API Token -->
        <div>
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">写入 API Token</label>
          <input v-model="settings.write_api_token" type="password" autocomplete="new-password"
                 :placeholder="settings.write_api_token_configured ? '已配置，留空保持当前值不变' : '未配置，输入新值后保存'"
                 class="w-full px-3 py-2 text-xs font-mono rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500">
          <p class="text-[10px] text-slate-400 mt-1">外部脚本/CI 写入节点时的凭据</p>
        </div>
      </div>
    </div>

    <!-- 模块 2: 管理员权威分流规则 -->
    <div class="space-y-4">
      <div class="p-3.5 rounded-xl bg-purple-50 dark:bg-purple-950/30 border border-purple-200 dark:border-purple-800/50 text-xs text-purple-800 dark:text-purple-300 flex items-start gap-2.5">
        <i class="fa-solid fa-circle-info text-purple-600 dark:text-purple-400 mt-0.5 shrink-0"></i>
        <div class="leading-relaxed">
          <strong>权威规则注入说明：</strong>管理员在此设定的规则拥有系统最高优先级。生成客户端订阅时，<strong>强制直连域名</strong>居于顶部优先匹配，随后是<strong>强制代理域名</strong>，之后注入用户自定义规则，最后是兜底分流。
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- 强制直连域名 -->
        <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-750/30 flex flex-col">
          <div class="flex items-center justify-between mb-1.5">
            <label class="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
              <i class="fa-solid fa-arrow-turn-down text-emerald-500"></i>
              <span>强制直连域名</span>
            </label>
            <span class="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">最高直连优先级</span>
          </div>
          <p class="text-[11px] text-slate-400 mb-2 leading-tight">每行一个域名或通配符（支持 +.domain.com），绕过代理直连。</p>
          <textarea v-model="rules.admin_direct_domains" rows="7" placeholder="ying-qing.cn&#10;+.corp.internal&#10;192.168.0.0/16" 
                    class="w-full flex-1 p-3 text-xs font-mono rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 resize-none leading-relaxed"></textarea>
        </div>

        <!-- 强制普通代理域名 -->
        <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-750/30 flex flex-col">
          <div class="flex items-center justify-between mb-1.5">
            <label class="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
              <i class="fa-solid fa-paper-plane text-sky-500"></i>
              <span>强制普通代理域名（走主出站）</span>
            </label>
            <span class="text-[10px] text-sky-600 dark:text-sky-400 font-medium">可覆盖内置高级规则</span>
          </div>
          <p class="text-[11px] text-slate-400 mb-2 leading-tight">每行一个域名，强制走便宜普通「主出站」（也可用来把内置高级域名踢回普通线路）。</p>
          <textarea v-model="rules.admin_proxy_domains" rows="7" placeholder="google.com&#10;+.github.com&#10;youtube.com" 
                    class="w-full flex-1 p-3 text-xs font-mono rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 resize-none leading-relaxed"></textarea>
        </div>

        <!-- 精选高级域名 -->
        <div class="p-4 rounded-xl border border-amber-200/80 dark:border-amber-800/50 bg-amber-50/40 dark:bg-amber-950/20 flex flex-col space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
              <i class="fa-solid fa-star text-amber-500"></i>
              <span>追加精选高级域名（走「精选高级」组）</span>
            </label>
            <span class="text-[10px] text-amber-700 dark:text-amber-400 font-medium">实时热追加</span>
          </div>
          <p class="text-[11px] text-slate-500 dark:text-slate-400 leading-tight">每行或逗号填一个域名后缀，出现新 AI/高风控服务时直接填这里，无需改代码。</p>
          <textarea v-model="rules.admin_premium_domains" rows="6" placeholder="sora.com&#10;manus.im&#10;example-ai.google" 
                    class="w-full flex-1 p-3 text-xs font-mono rounded-xl border border-amber-300 dark:border-amber-800 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none leading-relaxed"></textarea>
          <div v-if="defaultPremiumDomains.length" class="text-[11px]">
            <button type="button" @click="showDefaultPremium = !showDefaultPremium" class="text-amber-700 dark:text-amber-400 hover:underline flex items-center gap-1 cursor-pointer">
              <i class="fa-solid text-[10px]" :class="showDefaultPremium ? 'fa-chevron-down' : 'fa-chevron-right'"></i>
              <span>查看系统内置默认精选高级域名（共 {{ defaultPremiumDomains.length }} 个）</span>
            </button>
            <div v-if="showDefaultPremium" class="mt-1.5 p-2 rounded-lg bg-white/80 dark:bg-slate-900/70 border border-amber-200/60 dark:border-amber-800/40 font-mono text-[10px] text-slate-600 dark:text-slate-300 max-h-24 overflow-y-auto leading-relaxed">
              {{ defaultPremiumDomains.join(', ') }}
            </div>
          </div>
        </div>

        <!-- 管理员 Clash 规则 -->
        <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-750/30 flex flex-col">
          <div class="flex items-center justify-between mb-1.5">
            <label class="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
              <i class="fa-solid fa-code text-indigo-500"></i>
              <span>原生 Clash 规则</span>
            </label>
            <span class="text-[10px] text-indigo-600 dark:text-indigo-400 font-medium">支持占位符</span>
          </div>
          <p class="text-[11px] text-slate-400 mb-2 leading-tight">每行一条 Clash 规则，<code>__MAIN_PROXY__</code> 替换为主出站，<code>__PREMIUM_PROXY__</code> 替换为「精选高级」。</p>
          <textarea v-model="rules.admin_rules" rows="7" placeholder="DOMAIN-SUFFIX,example.com,__MAIN_PROXY__&#10;DOMAIN-SUFFIX,special-ai.com,__PREMIUM_PROXY__&#10;IP-CIDR,10.0.0.0/8,DIRECT" 
                    class="w-full flex-1 p-3 text-xs font-mono rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 resize-none leading-relaxed"></textarea>
        </div>
      </div>
    </div>

    <!-- 底部保存按钮 -->
    <div class="pt-4 border-t border-slate-200 dark:border-slate-700 flex items-center justify-end gap-3 shrink-0">
      <button :disabled="saving" @click="save" 
              class="px-6 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md shadow-purple-600/20 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50">
        <i v-if="saving" class="fa-solid fa-circle-notch fa-spin"></i>
        <i v-else class="fa-solid fa-floppy-disk"></i>
        <span>{{ saving ? '正在保存中...' : '保存全局规则与设置' }}</span>
      </button>
    </div>
  </div>
</template>

<script>
import { onMounted, reactive, ref } from 'vue';

export default {
  name: 'AdminRules',
  setup() {
    const rules = reactive({
      admin_direct_domains: '',
      admin_proxy_domains: '',
      admin_premium_domains: '',
      admin_rules: ''
    });
    const defaultPremiumDomains = ref([]);
    const showDefaultPremium = ref(false);

    const settings = reactive({
      default_target: 'clash',
      update_interval: 12,
      write_api_token: '',
      write_api_token_configured: false
    });

    const loading = ref(false);
    const saving = ref(false);
    const message = ref('');
    const error = ref(false);

    const load = async () => {
      loading.value = true;
      try {
        const response = await fetch('/api/admin/rules');
        if (response.status === 401 || response.status === 403) {
          window.location.href = '/login';
          return;
        }
        if (!response.ok) {
          error.value = true;
          message.value = '无法读取管理员规则';
          return;
        }
        const rulesData = await response.json();
        rules.admin_direct_domains = rulesData.admin_direct_domains || '';
        rules.admin_proxy_domains = rulesData.admin_proxy_domains || '';
        rules.admin_premium_domains = rulesData.admin_premium_domains || '';
        rules.admin_rules = rulesData.admin_rules || '';
        defaultPremiumDomains.value = Array.isArray(rulesData.default_premium_domains) ? rulesData.default_premium_domains : [];

        const settingsResponse = await fetch('/api/admin/settings');
        if (settingsResponse.ok) {
          const s = await settingsResponse.json();
          Object.assign(settings, s, { write_api_token: '' });
        }
      } catch (e) {
        error.value = true;
        message.value = '网络请求失败，无法加载规则';
      } finally {
        loading.value = false;
      }
    };

    const save = async () => {
      saving.value = true;
      message.value = '';
      error.value = false;
      try {
        const response = await fetch('/api/admin/rules', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(rules)
        });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail || '保存规则失败');
        }

        const settingsPayload = {
          default_target: settings.default_target,
          update_interval: settings.update_interval
        };
        const trimmedToken = settings.write_api_token.trim();
        if (trimmedToken) {
          settingsPayload.write_api_token = trimmedToken;
        }

        const settingsResponse = await fetch('/api/admin/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(settingsPayload)
        });
        if (!settingsResponse.ok) {
          const data = await settingsResponse.json();
          throw new Error(data.detail || '保存全局设置失败');
        }
        if (trimmedToken) {
          settings.write_api_token_configured = true;
          settings.write_api_token = '';
        }

        message.value = '全局规则与设置已成功保存！所有客户端订阅将实时生效。';
      } catch (e) {
        error.value = true;
        message.value = e.message;
      } finally {
        saving.value = false;
      }
    };

    onMounted(load);

    return {
      rules,
      defaultPremiumDomains,
      showDefaultPremium,
      settings,
      loading,
      saving,
      message,
      error,
      load,
      save
    };
  }
};
</script>
