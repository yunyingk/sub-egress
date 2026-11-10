<template>
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div class="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl max-w-xl w-full p-6 space-y-5 max-h-[92vh] flex flex-col">
        <!-- 弹窗标题 -->
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-700 pb-3 shrink-0">
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-lg bg-sky-100 dark:bg-sky-950 text-sky-600 dark:text-sky-400 flex items-center justify-center">
              <i class="fa-solid fa-sliders"></i>
            </div>
            <div>
              <h3 class="font-bold text-base text-slate-900 dark:text-white">订阅偏好与分流规则设置</h3>
              <p class="text-xs text-slate-500 dark:text-slate-400">配置用户级直连域名、双出站端口与自定义规则</p>
            </div>
          </div>
          <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <i class="fa-solid fa-xmark text-lg"></i>
          </button>
        </div>

        <!-- 标签页导航 -->
        <div class="flex border-b border-slate-200 dark:border-slate-700 shrink-0">
          <button @click="activeTab = 'rules'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-bold': activeTab === 'rules', 'border-transparent text-slate-500': activeTab !== 'rules'}"
                  class="pb-2.5 px-4 text-xs border-b-2 transition-all flex items-center gap-1.5">
            <i class="fa-solid fa-route"></i>
            <span>直连与分流规则 (用户级)</span>
          </button>
          <button @click="activeTab = 'ports'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-bold': activeTab === 'ports', 'border-transparent text-slate-500': activeTab !== 'ports'}"
                  class="pb-2.5 px-4 text-xs border-b-2 transition-all flex items-center gap-1.5">
            <i class="fa-solid fa-network-wired"></i>
            <span>双端口与订阅参数</span>
          </button>
          <button v-if="false" @click="activeTab = 'security'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-bold': activeTab === 'security', 'border-transparent text-slate-500': activeTab !== 'security'}"
                  class="pb-2.5 px-4 text-xs border-b-2 transition-all flex items-center gap-1.5">
            <i class="fa-solid fa-key"></i>
            <span>安全令牌</span>
          </button>
        </div>

        <!-- 表单主体 (支持内部滚动) -->
        <div class="flex-1 overflow-y-auto space-y-4 pr-1">

          <!-- TAB 1: 域名直连与分流规则 (用户级核心) -->
          <div v-if="activeTab === 'rules'" class="space-y-4">
            <!-- 1. 强制直连域名清单 -->
            <div class="p-3.5 rounded-xl bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-200/80 dark:border-emerald-800/60 space-y-2">
              <div class="flex items-center justify-between">
                <label class="block text-xs font-bold text-emerald-900 dark:text-emerald-200 flex items-center gap-1.5">
                  <i class="fa-solid fa-shield-halved text-emerald-600"></i>
                  <span>强制直连域名清单 (Custom Direct Domains)</span>
                </label>
                <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900 text-emerald-800 dark:text-emerald-200 font-bold">
                  DIRECT 置顶
                </span>
              </div>
              <p class="text-[11px] text-emerald-800 dark:text-emerald-300/80 leading-relaxed">
                这些域名及其子域名将作为<strong>最高优先级规则</strong>直接走本地直连出站，绝不经过任何代理节点，且自动注入 DNS <span class="font-mono font-bold">fake-ip-filter</span> 避障白名单。
              </p>
              <textarea v-model="editSettings.custom_direct_domains" rows="3" 
                        placeholder="每行一个或逗号分隔，例如:&#10;ying-qing.cn&#10;hosecloud.com&#10;ekuaibao.com"
                        class="w-full px-3 py-2 text-xs font-mono rounded-lg border border-emerald-300 dark:border-emerald-800 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"></textarea>
              <div class="text-[10px] text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
                <i class="fa-solid fa-circle-info"></i>
                <span>默认已包含 <code class="font-bold">ying-qing.cn</code>，确保您的家庭内网穿透与私有云服务永久直连。</span>
              </div>
            </div>

            <!-- 2. 强制代理域名清单 -->
            <div>
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                强制走主代理域名 (Custom Proxy Domains)
              </label>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mb-2">
                需要强制经由主出站代理分流的自定义海外域名（逗号或换行分隔）。
              </p>
              <input v-model="editSettings.custom_proxy_domains" type="text" placeholder="例如: huggingface.co, docker.io"
                     class="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
            </div>

            <!-- 3. 自定义原生 Clash 分流规则注入 -->
            <div>
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                原生 Clash 自定义分流规则注入 (Custom Rules Inject)
              </label>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mb-2">
                直接注入到订阅配置的规则流中（支持 DOMAIN-KEYWORD, IP-CIDR 等），支持注释。
              </p>
              <textarea v-model="editSettings.custom_rules" rows="3" 
                        placeholder="例如:&#10;DOMAIN-KEYWORD,google,PROXY&#10;IP-CIDR,192.168.100.0/24,DIRECT"
                        class="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"></textarea>
            </div>
          </div>

          <!-- TAB 2: 双端口与订阅参数 -->
          <div v-else-if="activeTab === 'ports'" class="space-y-4">
            <!-- 订阅卡片展示名称 (Profile Title) -->
            <div>
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">客户端卡片订阅名称 (Profile Title)</label>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mb-2">导入到 Clash Verge、Mihomo、Sing-box 客户端卡片顶部呈现的精致名称。</p>
              <input v-model="editSettings.subscription_title" type="text" placeholder="例如: sub-egress 出站聚合中枢"
                     class="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
            </div>

            <!-- Clash 原生双端口监听机制 (Dual-Port Listeners) -->
            <div class="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 space-y-3">
              <div class="flex items-center justify-between">
                <div>
                  <span class="text-xs font-bold text-slate-800 dark:text-slate-200 block">Clash 双端口机制 (Dual-Port Listeners)</span>
                  <span class="text-[11px] text-slate-500 dark:text-slate-400 block">原生下发双端口，主端口走 PROXY，副端口绑定『终端-日本』供命令行高速直连。</span>
                </div>
                <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/70 text-emerald-700 dark:text-emerald-300 font-semibold">原生直下</span>
              </div>
              <div class="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">主混合端口 (Mixed Port)</label>
                  <input v-model="editSettings.clash_mixed_port" type="number" placeholder="7897"
                         class="w-full px-2.5 py-1.5 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
                  <span class="text-[10px] text-slate-400 dark:text-slate-500">主流量/TUN (px-home 默认 7897)</span>
                </div>
                <div>
                  <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">终端副端口 (Terminal Port)</label>
                  <input v-model="editSettings.clash_terminal_port" type="number" placeholder="7898"
                         class="w-full px-2.5 py-1.5 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
                  <span class="text-[10px] text-slate-400 dark:text-slate-500">终端高速走日本 (px-7898 默认 7898)</span>
                </div>
              </div>
            </div>

            <!-- 默认导出内核 -->
          <div v-if="false">
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">默认订阅内核类型 (Default Target)</label>
              <select v-model="editSettings.default_target" class="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200">
                <option value="clash">Clash / Mihomo (YAML)</option>
                <option value="sing-box">Sing-box (JSON)</option>
                <option value="base64">Base64 / 通用 URI 列表</option>
              </select>
            </div>

            <!-- 客户端更新周期 -->
          <div v-if="false">
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">客户端更新间隔提示 (小时)</label>
              <input v-model="editSettings.update_interval" type="number" min="1" max="72"
                     class="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200">
            </div>
          </div>

          <!-- TAB 3: 安全令牌与权限 -->
          <div v-else-if="activeTab === 'security'" class="space-y-4" v-if="false">
            <!-- 订阅哈希安全令牌 -->
            <div>
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                订阅专属安全 Hash 令牌 (Subscription Token)
              </label>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mb-2">保护下游订阅免遭公网探测，混淆在 URL 路径中。</p>
              <div class="flex items-center gap-2">
                <input v-model="editSettings.sub_hash_token" type="text" readonly
                       class="flex-1 px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500">
                <button @click="handleGenerate" title="随机生成新令牌" 
                        class="px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition font-medium">
                  <i class="fa-solid fa-shuffle mr-1"></i> 随机
                </button>
              </div>
            </div>

            <!-- 访问控制模式 -->
            <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div>
                <span class="text-xs font-bold text-slate-800 dark:text-slate-200 block">强制携带安全令牌 (Token Enforce)</span>
                <span class="text-[11px] text-slate-500 dark:text-slate-400 block">开启后，未携带合法安全令牌的访问将直接返回 403 阻断；关闭则为宽松模式。</span>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input v-model="editSettings.require_token" type="checkbox" class="sr-only peer">
                <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sky-600"></div>
              </label>
            </div>

            <!-- 写入管理 API Token -->
            <div>
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">管理写入 API Key (Write Token)</label>
              <input v-model="editSettings.write_api_token" type="text" placeholder="留空则不校验管理写入权限"
                     class="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200">
            </div>
          </div>
        </div>

        <!-- 底部操作按钮 -->
        <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-700 shrink-0">
          <button @click="$emit('close')" class="px-4 py-2 text-xs font-medium rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition">
            取消
          </button>
          <button @click="handleSave" :disabled="saving" class="px-4 py-2 text-xs font-bold rounded-lg bg-sky-600 hover:bg-sky-500 text-white shadow-xs transition flex items-center gap-1.5 disabled:opacity-50">
            <i class="fa-solid fa-check" :class="{'fa-spin': saving}"></i>
            <span>{{ saving ? '保存中...' : '保存配置' }}</span>
          </button>
        </div>
      </div>
    </div>
  
</template>

<script>
import { ref, watch } from 'vue';

export default {
  name: 'SettingsModal',
  props: {
    visible: { type: Boolean, default: false },
    settings: { type: Object, required: true },
    saving: { type: Boolean, default: false }
  },
  emits: ['close', 'save', 'regenerateToken'],
  setup(props, { emit }) {
    const activeTab = ref('rules'); // 默认展示用户最关心的分流规则配置
    const editSettings = ref({});

    watch(() => props.visible, (val) => {
      if (val) {
        const copy = JSON.parse(JSON.stringify(props.settings || {}));
        if (!copy.clash_mixed_port) copy.clash_mixed_port = '7897';
        if (!copy.clash_terminal_port) copy.clash_terminal_port = '7898';
        if (copy.custom_direct_domains === undefined || copy.custom_direct_domains === null) {
          copy.custom_direct_domains = 'ying-qing.cn';
        }
        if (copy.custom_proxy_domains === undefined) copy.custom_proxy_domains = '';
        if (copy.custom_rules === undefined) copy.custom_rules = '';
        editSettings.value = copy;
      }
    });

    const handleGenerate = async () => {
      try {
        const res = await fetch('/api/user/regenerate-token', { method: 'POST' });
        const data = await res.json();
        if (data.new_token) {
          editSettings.value.sub_hash_token = data.new_token;
        }
      } catch (e) {
        console.error('Failed to regenerate token', e);
      }
    };

    const handleSave = () => {
      emit('save', editSettings.value);
    };

    return {
      activeTab,
      editSettings,
      handleGenerate,
      handleSave
    };
  }
};
</script>
