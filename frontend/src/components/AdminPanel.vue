<template>
  <div v-if="visible" class="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 w-full p-6 md:p-8 min-h-[70vh] flex flex-col space-y-4">
    <!-- 标题栏与刷新 -->
    <div class="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-700 shrink-0">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 flex items-center justify-center">
          <i class="fa-solid fa-users-gear text-lg"></i>
        </div>
        <div>
          <h3 class="text-lg font-bold text-slate-900 dark:text-white">系统管理大盘 · 多租户用户管理</h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">管控多用户生命周期、专属订阅令牌、通行密钥与安全凭证</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button @click="fetchUsers" class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1.5 cursor-pointer">
          <i class="fa-solid fa-arrows-rotate" :class="{'fa-spin': loading}"></i>刷新
        </button>
      </div>
    </div>

        <!-- 提示栏 -->
        <div v-if="errorMessage" class="mb-3 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center justify-between gap-2 shrink-0">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-circle-exclamation shrink-0"></i>
            <span>{{ errorMessage }}</span>
          </div>
          <button @click="errorMessage = ''" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 cursor-pointer">
            <i class="fa-solid fa-xmark"></i>
          </button>
        </div>
        <div v-if="successMessage" class="mb-3 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs flex items-center justify-between gap-2 shrink-0">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-circle-check shrink-0"></i>
            <span>{{ successMessage }}</span>
          </div>
          <button @click="successMessage = ''" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 cursor-pointer">
            <i class="fa-solid fa-xmark"></i>
          </button>
        </div>

        <!-- 创建用户成功专属卡片 (带快捷复制密码) -->
        <div v-if="createdUser" class="mb-4 p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 text-xs flex flex-wrap items-center justify-between gap-3 shrink-0 shadow-xs">
          <div class="flex items-center gap-2 flex-wrap min-w-0">
            <i class="fa-solid fa-circle-check text-emerald-600 dark:text-emerald-400 text-base shrink-0"></i>
            <span class="font-medium">用户 <strong>{{ createdUser.username }}</strong> 已创建，初始密码：</span>
            <code class="px-2.5 py-1 rounded-lg bg-white dark:bg-slate-900 border border-emerald-300 dark:border-emerald-700 font-mono text-[12px] text-emerald-950 dark:text-emerald-100 select-all break-all">{{ createdUser.password }}</code>
          </div>
          <div class="flex items-center gap-2">
            <button type="button" @click="copyText(createdUser.password)" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 transition-all shadow-xs cursor-pointer">
              <i class="fa-regular" :class="copyStateText === createdUser.password ? 'fa-circle-check text-white' : 'fa-copy'"></i>
              <span>{{ copyStateText === createdUser.password ? '已复制密码！' : '一键复制密码' }}</span>
            </button>
            <button type="button" @click="createdUser = null" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 cursor-pointer">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
        </div>

    <!-- 创建新租户用户 -->
    <form class="flex flex-wrap items-center gap-2.5 p-3.5 rounded-xl bg-slate-50 dark:bg-slate-750/50 border border-slate-200 dark:border-slate-700" @submit.prevent="createUser">
      <div class="relative flex-1 min-w-[200px]">
        <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
          <i class="fa-regular fa-user"></i>
        </span>
        <input v-model="newUsername" required minlength="5" maxlength="20" pattern="[a-z0-9_-]+" placeholder="新用户名（5–20位小写与数字）" 
               class="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500">
      </div>
      <div class="relative flex-1 min-w-[200px]">
        <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
          <i class="fa-solid fa-lock"></i>
        </span>
        <input v-model="newUserPassword" minlength="20" maxlength="260" placeholder="初始密码（留空自动生成 32 位合规强密码）" 
               class="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 font-mono focus:outline-none focus:ring-2 focus:ring-sky-500">
      </div>
      <button type="submit" :disabled="loading" 
              class="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 cursor-pointer transition-all disabled:opacity-50">
        <i class="fa-solid fa-user-plus"></i>
        <span>创建用户</span>
      </button>
    </form>

        <!-- 用户列表表格 (自适应滚动) -->
        <div class="flex-1 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-xl">
          <table class="w-full text-left text-xs text-slate-700 dark:text-slate-300">
            <thead class="bg-slate-50 dark:bg-slate-750 text-slate-500 dark:text-slate-400 uppercase font-semibold text-[11px] sticky top-0 z-10 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th class="px-4 py-3">ID / 用户名</th>
                <th class="px-4 py-3">角色权限</th>
                <th class="px-4 py-3">账号状态</th>
                <th class="px-4 py-3">专属订阅令牌 (Token)</th>
                <th class="px-4 py-3">通行密钥</th>
                <th class="px-4 py-3">第三方授权</th>
                <th class="px-4 py-3 text-right">操作管理</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
              <tr v-for="u in users" :key="u.id" class="hover:bg-slate-50 dark:hover:bg-slate-750/50 transition-colors">
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-slate-900 dark:text-white">{{ u.username }}</span>
                    <span class="text-[10px] text-slate-400 font-mono">#{{ u.id }}</span>
                  </div>
                  <div class="text-[10px] text-slate-400 mt-0.5">注册: {{ u.created_at ? u.created_at.slice(0, 10) : '-' }}</div>
                </td>
                <td class="px-4 py-3">
                  <span v-if="u.role === 'admin'" class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
                    管理员
                  </span>
                  <span v-else class="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    普通成员
                  </span>
                </td>
                <td class="px-4 py-3">
                  <span v-if="u.is_active" class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                    正常活跃
                  </span>
                  <span v-else class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
                    已被禁用
                  </span>
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-1.5 font-mono text-[11px] text-slate-600 dark:text-slate-300">
                    <span>{{ u.sub_hash_token.slice(0, 12) }}...{{ u.sub_hash_token.slice(-6) }}</span>
                    <button @click="copyText(u.sub_hash_token)" title="复制完整令牌" class="text-sky-500 hover:text-sky-600 cursor-pointer p-0.5">
                      <i class="fa-regular" :class="copyStateText === u.sub_hash_token ? 'fa-circle-check text-emerald-500' : 'fa-copy'"></i>
                    </button>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <div v-if="u.passkeys && u.passkeys.length > 0" class="space-y-1.5">
                    <div v-for="pk in u.passkeys" :key="pk.id" class="flex items-center gap-1.5 text-[11px] relative">
                      <i class="fa-solid fa-fingerprint text-sky-500 shrink-0"></i>
                      <span class="truncate max-w-[120px]" :title="pk.name">{{ pk.name }}</span>
                      
                      <!-- 就近解绑按钮与浮层确认气泡 -->
                      <div class="relative inline-block">
                        <button @click.stop="toggleConfirm(`pk-${u.id}-${pk.id}`, `确定为该用户解绑通行密钥【${pk.name}】？`, () => unbindPasskey(u.id, pk.id))" 
                                title="解绑该通行密钥" 
                                class="text-rose-400 hover:text-rose-600 p-0.5 cursor-pointer">
                          <i class="fa-solid fa-xmark"></i>
                        </button>
                        
                        <!-- 悬浮弹窗 -->
                        <div v-if="activeConfirm && activeConfirm.id === `pk-${u.id}-${pk.id}`" 
                             @click.stop 
                             class="absolute left-0 bottom-full mb-1 z-40 w-52 p-3 bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 text-xs text-left">
                          <div class="flex items-start gap-1.5 mb-2 text-slate-800 dark:text-slate-200">
                            <i class="fa-solid fa-triangle-exclamation text-amber-500 mt-0.5 shrink-0"></i>
                            <span class="text-[11px] leading-tight">{{ activeConfirm.msg }}</span>
                          </div>
                          <div class="flex justify-end gap-1.5">
                            <button @click="activeConfirm = null" class="px-2 py-0.5 text-[11px] rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer">取消</button>
                            <button @click="runConfirm" class="px-2 py-0.5 text-[11px] rounded bg-rose-600 hover:bg-rose-500 text-white font-medium cursor-pointer">确定解绑</button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <span v-else class="text-[11px] text-slate-400">无</span>
                </td>
                <td class="px-4 py-3">
                  <div v-if="(u.identities && u.identities.length) || u.oauth_provider" class="flex flex-wrap items-center gap-1.5">
                    <div v-for="idItem in (u.identities && u.identities.length ? u.identities : [{ provider: u.oauth_provider, subject: u.oauth_id }])"
                         :key="idItem.provider + (idItem.id || idItem.subject || '')"
                         class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium"
                         :class="idItem.provider === 'github' ? 'bg-slate-100 dark:bg-slate-750 text-slate-800 dark:text-slate-200 border border-slate-300 dark:border-slate-600' : 'bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300 border border-sky-200 dark:border-sky-800'">
                      <i :class="idItem.provider === 'github' ? 'fa-brands fa-github' : 'fa-solid fa-id-card-clip'"></i>
                      <span>{{ idItem.provider }}</span>
                      <span v-if="idItem.subject" class="font-mono text-[9px] opacity-75">({{ idItem.subject }})</span>
                    </div>

                    <div class="relative inline-block ml-0.5">
                      <button @click.stop="toggleConfirm(`oauth-${u.id}`, `确定解除用户 [${u.username}] 的第三方授权绑定吗？`, () => unbindOAuth(u))" 
                              title="解除第三方授权" 
                              class="text-rose-400 hover:text-rose-600 p-0.5 cursor-pointer">
                        <i class="fa-solid fa-link-slash"></i>
                      </button>
                      
                      <!-- 悬浮弹窗 -->
                      <div v-if="activeConfirm && activeConfirm.id === `oauth-${u.id}`" 
                           @click.stop 
                           class="absolute left-0 bottom-full mb-1 z-40 w-52 p-3 bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 text-xs text-left">
                        <div class="flex items-start gap-1.5 mb-2 text-slate-800 dark:text-slate-200">
                          <i class="fa-solid fa-triangle-exclamation text-amber-500 mt-0.5 shrink-0"></i>
                          <span class="text-[11px] leading-tight">{{ activeConfirm.msg }}</span>
                        </div>
                        <div class="flex justify-end gap-1.5">
                          <button @click="activeConfirm = null" class="px-2 py-0.5 text-[11px] rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer">取消</button>
                          <button @click="runConfirm" class="px-2 py-0.5 text-[11px] rounded bg-rose-600 hover:bg-rose-500 text-white font-medium cursor-pointer">确定解除</button>
                        </div>
                      </div>
                    </div>
                  </div>
                  <span v-else class="text-[11px] text-slate-400">未绑定</span>
                </td>
                <td class="px-4 py-3 text-right whitespace-nowrap">
                  <div class="flex items-center justify-end gap-1.5">
                    <!-- 重置密码 (自身管理员不可点) -->
                    <button v-if="u.id !== currentAdmin.id" @click="openResetPasswordModal(u)"
                            class="px-2.5 py-1 text-xs rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1 cursor-pointer">
                      <i class="fa-solid fa-key text-amber-500"></i>
                      <span>重设密码</span>
                    </button>
                    <span v-else class="px-2 py-1 text-[11px] text-slate-400 italic">自身密码不可重设</span>

                    <!-- 激活 / 禁用 (就近悬浮确认) -->
                    <div v-if="u.id !== currentAdmin.id" class="relative inline-block">
                      <button v-if="u.is_active"
                              @click.stop="toggleConfirm(`deact-${u.id}`, `确定要禁用用户 [${u.username}] 吗？禁用后该用户将无法登录且无法获取订阅。`, () => deactivateUser(u))"
                              class="border-rose-200 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 px-2.5 py-1 text-xs rounded-lg border transition-all cursor-pointer">
                        禁用
                      </button>
                      <button v-else
                              @click="activateUser(u)"
                              class="border-emerald-200 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 px-2.5 py-1 text-xs rounded-lg border transition-all cursor-pointer">
                        激活
                      </button>
                      
                      <!-- 悬浮弹窗 -->
                      <div v-if="activeConfirm && activeConfirm.id === `deact-${u.id}`" 
                           @click.stop 
                           class="absolute right-0 bottom-full mb-1 z-40 w-52 p-3 bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 text-xs text-left">
                        <div class="flex items-start gap-1.5 mb-2 text-slate-800 dark:text-slate-200">
                          <i class="fa-solid fa-triangle-exclamation text-amber-500 mt-0.5 shrink-0"></i>
                          <span class="text-[11px] leading-tight">{{ activeConfirm.msg }}</span>
                        </div>
                        <div class="flex justify-end gap-1.5">
                          <button @click="activeConfirm = null" class="px-2 py-0.5 text-[11px] rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer">取消</button>
                          <button @click="runConfirm" class="px-2 py-0.5 text-[11px] rounded bg-rose-600 hover:bg-rose-500 text-white font-medium cursor-pointer">确定禁用</button>
                        </div>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

    <!-- 底部信息 -->
    <div class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between text-xs text-slate-400 shrink-0">
      <span>共 {{ users.length }} 个注册系统用户</span>
      <span class="text-[11px] text-slate-400">可在操作栏为指定用户重设密码、启用/禁用、或解绑外部身份</span>
    </div>

    <!-- 重设密码子弹窗 -->
    <div v-if="showResetModal" class="fixed inset-0 z-60 overflow-y-auto flex items-center justify-center p-4">
      <div class="fixed inset-0 bg-slate-900/70 backdrop-blur-xs" @click="showResetModal = false"></div>
      <div class="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 max-w-md w-full p-6 z-20">
          <h4 class="text-base font-bold text-slate-900 dark:text-white mb-2">
            重置用户 [{{ targetUser.username }}] 的密码
          </h4>
          <p class="text-xs text-slate-500 mb-4 leading-relaxed">
            重置密码必须符合全小写规范（严禁大写字母，长度 20~260 位）。您也可以留空直接自动生成 32 位安全强随机密码。
          </p>

          <div v-if="!resetResultPassword" class="space-y-3">
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="text-xs font-semibold text-slate-700 dark:text-slate-300">新密码</label>
                <button type="button" @click="generatePasswordForReset" class="text-xs text-sky-500 hover:underline">
                  <i class="fa-solid fa-wand-magic-sparkles mr-0.5"></i>自动生成 32 位随机密码
                </button>
              </div>
              <input v-model="newPasswordInput" type="text" placeholder="留空则自动生成或手动输入"
                     class="w-full px-3 py-2 text-xs font-mono rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700">
            </div>

            <div class="flex items-center justify-end gap-2 pt-2">
              <button @click="showResetModal = false" class="px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600">
                取消
              </button>
              <button @click="executeResetPassword" :disabled="resetLoading"
                      class="px-4 py-1.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white flex items-center gap-1.5 disabled:opacity-50">
                <i v-if="resetLoading" class="fa-solid fa-circle-notch fa-spin"></i>
                <span>立即重置</span>
              </button>
            </div>
          </div>

          <!-- 重置成功结果展示 -->
          <div v-else class="space-y-4">
            <div class="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 text-xs">
              <div class="font-bold mb-1">🎉 密码已成功重置！</div>
              <div>新密码如下（请立即复制并发给用户）:</div>
              <div class="mt-2 p-2 bg-white dark:bg-slate-900 rounded border border-emerald-300 dark:border-emerald-800 font-mono select-all break-all text-[11px]">
                {{ resetResultPassword }}
              </div>
            </div>
            <div class="flex justify-end gap-2">
              <button @click="copyText(resetResultPassword)" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white">
                <i class="fa-regular fa-copy mr-1"></i>复制新密码
              </button>
              <button @click="showResetModal = false" class="px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600">
                完成
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  
</template>

<script>
import { ref, reactive, onMounted } from 'vue';

export default {
  name: 'AdminPanel',
  props: {
    visible: { type: Boolean, default: false },
    currentAdmin: { type: Object, default: () => ({}) }
  },
  emits: ['close'],
  setup(props, { emit }) {
    const users = ref([]);
    const loading = ref(false);
    const errorMessage = ref('');
    const successMessage = ref('');
    const newUsername = ref('');
    const newUserPassword = ref('');
    const createdUser = ref(null);
    const copyStateText = ref('');
    const activeConfirm = ref(null);

    const toggleConfirm = (id, msg, onConfirm) => {
      if (activeConfirm.value && activeConfirm.value.id === id) {
        activeConfirm.value = null;
      } else {
        activeConfirm.value = { id, msg, onConfirm };
      }
    };

    const runConfirm = async () => {
      if (activeConfirm.value && typeof activeConfirm.value.onConfirm === 'function') {
        const fn = activeConfirm.value.onConfirm;
        activeConfirm.value = null;
        await fn();
      }
    };

    const copyText = async (txt) => {
      if (!txt) return;
      try {
        await navigator.clipboard.writeText(txt);
        copyStateText.value = txt;
        setTimeout(() => {
          if (copyStateText.value === txt) {
            copyStateText.value = '';
          }
        }, 2000);
      } catch (err) {
        errorMessage.value = '复制失败，请手动选中文本复制';
      }
    };

    const createUser = async () => {
      try {
        const response = await fetch('/api/admin/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: newUsername.value,
            password: newUserPassword.value || null
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '创建失败');
        createdUser.value = { username: data.username, password: data.initial_password };
        newUsername.value = '';
        newUserPassword.value = '';
        await fetchUsers();
      } catch (error) {
        errorMessage.value = error.message;
      }
    };

    // 重置密码弹窗状态
    const showResetModal = ref(false);
    const targetUser = ref(null);
    const newPasswordInput = ref('');
    const resetLoading = ref(false);
    const resetResultPassword = ref('');

    // 加载用户列表
    const fetchUsers = async () => {
      loading.value = true;
      errorMessage.value = '';
      try {
        const res = await fetch('/api/admin/users');
        if (res.ok) {
          users.value = await res.json();
        } else {
          const err = await res.json();
          errorMessage.value = err.detail || '获取用户列表失败';
        }
      } catch (e) {
        errorMessage.value = '请求失败，请稍后重试';
      } finally {
        loading.value = false;
      }
    };

    // 激活用户
    const activateUser = async (user) => {
      try {
        const res = await fetch(`/api/admin/users/${user.id}/activate`, { method: 'POST' });
        if (res.ok) {
          user.is_active = true;
          successMessage.value = `用户 ${user.username} 已激活`;
        }
      } catch (e) {
        errorMessage.value = '激活失败';
      }
    };

    // 禁用用户
    const deactivateUser = async (user) => {
      if (user.id === props.currentAdmin.id) {
        errorMessage.value = '管理员不能禁用自身账号！';
        return;
      }
      try {
        const res = await fetch(`/api/admin/users/${user.id}/deactivate`, { method: 'POST' });
        if (res.ok) {
          user.is_active = false;
          successMessage.value = `用户 ${user.username} 已禁用`;
        } else {
          const data = await res.json();
          errorMessage.value = data.detail || '禁用失败';
        }
      } catch (e) {
        errorMessage.value = '禁用失败';
      }
    };

    // 打开重置密码弹窗
    const openResetPasswordModal = (user) => {
      if (user.id === props.currentAdmin.id) {
        errorMessage.value = '管理员不能在管理页面重置自身的密码！若需修改自身密码请使用个人安全中心，若遗忘密码请通过服务器重启配置 RESET_ADMIN_PASSWORD 重设。';
        return;
      }
      targetUser.value = user;
      newPasswordInput.value = '';
      resetResultPassword.value = '';
      showResetModal.value = true;
    };

    // 生成随机合规密码
    const generatePasswordForReset = () => {
      const lowers = 'abcdefghijklmnopqrstuvwxyz';
      const digits = '0123456789';
      const symbols = '!@#%&*+-=._';
      const all = lowers + digits + symbols;
      let pwd = [
        lowers[Math.floor(Math.random() * lowers.length)],
        digits[Math.floor(Math.random() * digits.length)],
        symbols[Math.floor(Math.random() * symbols.length)]
      ];
      for (let i = 3; i < 32; i++) {
        pwd.push(all[Math.floor(Math.random() * all.length)]);
      }
      pwd.sort(() => Math.random() - 0.5);
      newPasswordInput.value = pwd.join('');
    };

    // 执行重置用户密码
    const executeResetPassword = async () => {
      if (!targetUser.value) return;
      if (newPasswordInput.value && /[A-Z]/.test(newPasswordInput.value)) {
        errorMessage.value = '密码严禁包含大写字母！请使用小写字母、数字和符号。';
        return;
      }

      resetLoading.value = true;
      try {
        const res = await fetch(`/api/admin/users/${targetUser.value.id}/reset-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_password: newPasswordInput.value || null })
        });
        const data = await res.json();
        if (res.ok) {
          resetResultPassword.value = data.new_password;
          successMessage.value = `用户 ${targetUser.value.username} 的密码重置成功！`;
        } else {
          errorMessage.value = data.detail || '重置密码失败';
        }
      } catch (e) {
        errorMessage.value = '网络异常，请重试';
      } finally {
        resetLoading.value = false;
      }
    };

    // 解绑指定通行密钥
    const unbindPasskey = async (userId, passkeyId) => {
      try {
        const res = await fetch(`/api/admin/users/${userId}/passkeys/${passkeyId}`, { method: 'DELETE' });
        if (res.ok) {
          await fetchUsers();
          successMessage.value = '通行密钥解绑成功';
        } else {
          const data = await res.json();
          errorMessage.value = data.detail || '解绑失败';
        }
      } catch (e) {
        errorMessage.value = '解绑失败';
      }
    };

    // 解绑第三方授权
    const unbindOAuth = async (user) => {
      try {
        const res = await fetch(`/api/admin/users/${user.id}/unbind-oauth`, { method: 'POST' });
        if (res.ok) {
          user.oauth_provider = null;
          user.identities = [];
          successMessage.value = `用户 ${user.username} 的第三方绑定已解除`;
        } else {
          const data = await res.json();
          errorMessage.value = data.detail || '解除绑定失败';
        }
      } catch (e) {
        errorMessage.value = '解除绑定失败';
      }
    };

    onMounted(() => {
      fetchUsers();
      window.addEventListener('click', () => {
        activeConfirm.value = null;
      });
    });

    return {
      users,
      newUsername,
      newUserPassword,
      createdUser,
      copyStateText,
      activeConfirm,
      toggleConfirm,
      runConfirm,
      createUser,
      loading,
      errorMessage,
      successMessage,
      showResetModal,
      targetUser,
      newPasswordInput,
      resetLoading,
      resetResultPassword,
      fetchUsers,
      activateUser,
      deactivateUser,
      openResetPasswordModal,
      generatePasswordForReset,
      executeResetPassword,
      unbindPasskey,
      unbindOAuth,
      copyText
    };
  }
};
</script>
