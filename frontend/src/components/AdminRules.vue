<template>
  <main class="max-w-5xl mx-auto px-4 py-8 space-y-6">
    <header class="flex items-center justify-between">
      <div><h1 class="text-2xl font-bold">管理员全局规则</h1><p class="text-sm text-slate-500">规则会优先于每个用户的个人分流规则写入订阅。</p></div>
      <nav class="flex gap-2"><a class="px-3 py-2 rounded-lg border" href="/admin/users">用户管理</a><a class="px-3 py-2 rounded-lg bg-sky-600 text-white" href="/admin/rules">全局规则</a><button class="px-3 py-2 rounded-lg border" @click="logout">退出管理</button></nav>
    </header>
    <section class="bg-white dark:bg-slate-800 rounded-2xl border p-6 space-y-5">
      <h2 class="text-lg font-bold">全局订阅设置</h2>
      <label class="block">默认客户端内核<select v-model="settings.default_target" class="ml-3 rounded border p-2"><option value="clash">Clash / Mihomo</option><option value="sing-box">sing-box</option><option value="base64">Base64</option></select></label>
      <label class="block">更新间隔（小时）<input v-model.number="settings.update_interval" type="number" min="1" max="72" class="ml-3 rounded border p-2"></label>
      <label class="flex gap-2 items-center"><input v-model="settings.require_token" type="checkbox">订阅请求必须携带令牌</label>
      <label class="block">写入 API Token <input v-model="settings.write_api_token" type="password" autocomplete="new-password" placeholder="留空保持当前值" class="block w-full rounded border p-2 mt-2"></label>
      <div v-for="item in fields" :key="item.key"><label class="font-semibold">{{ item.label }}</label><p class="text-xs text-slate-500 mb-2">{{ item.help }}</p><textarea v-model="rules[item.key]" rows="5" class="w-full rounded-lg border p-3 font-mono text-sm bg-transparent" :placeholder="item.placeholder" /></div>
      <p v-if="message" :class="error ? 'text-rose-600' : 'text-emerald-600'">{{ message }}</p>
      <button class="px-4 py-2 rounded-lg bg-sky-600 text-white disabled:opacity-50" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存全局规则' }}</button>
    </section>
  </main>
</template>
<script>
import { onMounted, reactive, ref } from 'vue';
export default {
  setup() {
    const rules = reactive({ admin_direct_domains: '', admin_proxy_domains: '', admin_rules: '' });
    const settings = reactive({ require_token: false, default_target: 'clash', update_interval: 12, write_api_token: '' });
    const fields = [
      { key: 'admin_direct_domains', label: '管理员强制直连域名', help: '每行或逗号分隔；高于用户规则。', placeholder: 'example.cn' },
      { key: 'admin_proxy_domains', label: '管理员强制代理域名', help: '每行或逗号分隔；在管理员直连规则之后、用户规则之前。', placeholder: 'example.com' },
      { key: 'admin_rules', label: '管理员 Clash 规则', help: '每行一条规则，支持 __MAIN_PROXY__ 占位符。', placeholder: 'DOMAIN-SUFFIX,example.com,__MAIN_PROXY__' },
    ];
    const saving = ref(false), message = ref(''), error = ref(false);
    const load = async () => {
      const response = await fetch('/api/admin/rules');
      if (response.status === 401 || response.status === 403) { window.location.href = '/login'; return; }
      if (!response.ok) { error.value = true; message.value = '无法读取管理员规则'; return; }
      Object.assign(rules, await response.json());
      const settingsResponse = await fetch('/api/admin/settings');
      if (settingsResponse.ok) Object.assign(settings, await settingsResponse.json(), { write_api_token: '' });
    };
    const save = async () => {
      saving.value = true; message.value = ''; error.value = false;
      try {
        const response = await fetch('/api/admin/rules', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rules) });
        if (!response.ok) throw new Error((await response.json()).detail || '保存失败');
        const settingsResponse = await fetch('/api/admin/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) });
        if (!settingsResponse.ok) throw new Error((await settingsResponse.json()).detail || '全局设置保存失败');
        message.value = '全局规则已保存';
      } catch (e) { error.value = true; message.value = e.message; }
      finally { saving.value = false; }
    };
    const logout = async () => { await fetch('/api/auth/logout', { method: 'POST' }); window.location.href = '/login'; };
    onMounted(load);
    return { rules, settings, fields, saving, message, error, save, logout };
  }
};
</script>
