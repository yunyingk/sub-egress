import { ref, reactive, watch, computed } from 'vue';

// 辅助 Base64URL 转换函数
function bufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64urlToBuffer(base64url) {
  let base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) {
    base64 += '=';
  }
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) {
    output[i] = raw.charCodeAt(i);
  }
  return output.buffer;
}

function formatTime(isoStr) {
  if (!isoStr) return '从未使用';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  } catch (e) {
    return isoStr;
  }
}

export default {
  name: 'UserSecurityModal',
  props: {
    visible: { type: Boolean, default: false },
    user: { type: Object, default: () => ({}) }
  },
  emits: ['close', 'userUpdated'],
  setup(props, { emit }) {
    const activeTab = ref('passkeys'); // passkeys | password | oauth
    const loading = ref(false);
    const passkeys = ref([]);
    const newPasskeyName = ref('');
    const errorMessage = ref('');
    const successMessage = ref('');

    const isPasskeyLimitReached = computed(() => passkeys.value.length >= 5);

    // 修改密码表单
    const passwordForm = reactive({
      old_password: '',
      new_password: '',
      confirm_password: ''
    });

    const checkPasswordUppercase = (val) => {
      if (/[A-Z]/.test(val)) {
        errorMessage.value = '⚠️ 密码严禁包含大写字母，请使用小写字母、数字和符号';
      } else if (errorMessage.value.includes('密码严禁包含大写字母')) {
        errorMessage.value = '';
      }
    };

    const generatePassword = () => {
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
      const generated = pwd.join('');
      passwordForm.new_password = generated;
      passwordForm.confirm_password = generated;
      errorMessage.value = '';
      successMessage.value = '已自动为您生成 32 位全小写安全随机密码！';
    };

    // 加载当前用户的通行密钥
    const fetchPasskeys = async () => {
      try {
        const res = await fetch('/api/user/passkeys');
        if (res.ok) {
          passkeys.value = await res.json();
        }
      } catch (e) {
        console.error('Failed to load passkeys', e);
      }
    };

    // 绑定当前设备的新通行密钥 (最多 5 个限制)
    const registerPasskey = async () => {
      errorMessage.value = '';
      successMessage.value = '';

      if (isPasskeyLimitReached.value) {
        errorMessage.value = '每个账号最多只允许绑定 5 个通行密钥，已达到配额上限。';
        return;
      }

      if (!window.PublicKeyCredential) {
        errorMessage.value = '当前浏览器或系统不支持 WebAuthn 通行密钥。';
        return;
      }

      loading.value = true;
      try {
        const startRes = await fetch('/api/auth/passkey/register/start', { method: 'POST' });
        if (!startRes.ok) {
          const err = await startRes.json();
          throw new Error(err.detail || '获取注册挑战失败');
        }
        const options = await startRes.json();
        options.challenge = base64urlToBuffer(options.challenge);
        options.user.id = base64urlToBuffer(options.user.id);

        const credential = await navigator.credentials.create({
          publicKey: options
        });

        if (!credential) {
          throw new Error('未创建有效凭据');
        }

        const finishPayload = {
          id: credential.id,
          rawId: bufferToBase64url(credential.rawId),
          type: credential.type,
          name: newPasskeyName.value.trim() || '我的通行密钥',
          response: {
            clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
            attestationObject: bufferToBase64url(credential.response.attestationObject)
          }
        };

        const finishRes = await fetch('/api/auth/passkey/register/finish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(finishPayload)
        });
        const finishData = await finishRes.json();

        if (finishRes.ok) {
          successMessage.value = '🎉 成功绑定当前设备通行密钥！下次可直接指纹/面容免密登录。';
          newPasskeyName.value = '';
          await fetchPasskeys();
          emit('userUpdated');
        } else {
          errorMessage.value = finishData.detail || '绑定失败，请重试';
        }
      } catch (e) {
        if (e.name === 'NotAllowedError') {
          errorMessage.value = '已取消通行密钥绑定操作。';
        } else {
          errorMessage.value = e.message || '通行密钥绑定出错';
        }
      } finally {
        loading.value = false;
      }
    };

    // 解除已绑定的通行密钥
    const deletePasskey = async (id, name) => {
      if (!confirm(`确定要解绑通行密钥【${name}】吗？解绑后将无法使用该设备免密登录。`)) return;
      try {
        const res = await fetch(`/api/user/passkeys/${id}`, { method: 'DELETE' });
        if (res.ok) {
          successMessage.value = `通行密钥【${name}】已成功解绑`;
          await fetchPasskeys();
          emit('userUpdated');
        } else {
          const data = await res.json();
          errorMessage.value = data.detail || '解绑失败';
        }
      } catch (e) {
        console.error('Failed to delete passkey', e);
      }
    };

    // 提交修改密码
    const submitChangePassword = async () => {
      errorMessage.value = '';
      successMessage.value = '';

      if (passwordForm.new_password !== passwordForm.confirm_password) {
        errorMessage.value = '两次输入的新密码不一致！';
        return;
      }
      if (/[A-Z]/.test(passwordForm.new_password)) {
        errorMessage.value = '新密码严禁包含大写字母！请使用纯小写字母、数字与符号。';
        return;
      }
      if (passwordForm.new_password.length < 20 || passwordForm.new_password.length > 260) {
        errorMessage.value = '密码长度必须在 20~260 字符之间！';
        return;
      }

      loading.value = true;
      try {
        const res = await fetch('/api/auth/change-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            old_password: passwordForm.old_password || null,
            new_password: passwordForm.new_password
          })
        });
        const data = await res.json();
        if (res.ok) {
          successMessage.value = '密码修改成功！请妥善保存您的新密码。';
          passwordForm.old_password = '';
          passwordForm.new_password = '';
          passwordForm.confirm_password = '';
          emit('userUpdated');
        } else {
          errorMessage.value = data.detail || '修改密码失败';
        }
      } catch (e) {
        errorMessage.value = '网络请求异常，请稍后重试';
      } finally {
        loading.value = false;
      }
    };

    // 解除第三方统一登录授权 (Authentik SSO)
    const handleUnbindOAuth = async () => {
      if (!confirm('确定要解除第三方登录绑定吗？解除后将无法再通过 Authentik 单点登录直接进入此账号。')) return;
      errorMessage.value = '';
      successMessage.value = '';
      loading.value = true;

      try {
        const res = await fetch('/api/user/unbind-oauth', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          successMessage.value = '第三方登录已成功解除绑定！';
          emit('userUpdated');
        } else {
          errorMessage.value = data.detail || '解绑失败，请检查账号安全配置';
        }
      } catch (e) {
        errorMessage.value = '网络请求异常，请稍后重试';
      } finally {
        loading.value = false;
      }
    };

    // 绑定当前第三方统一登录授权 (Authentik SSO)
    const handleBindOAuth = async () => {
      errorMessage.value = '';
      successMessage.value = '';
      loading.value = true;

      try {
        const res = await fetch('/api/user/bind-oauth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: 'authentik' })
        });
        const data = await res.json();
        if (res.ok) {
          successMessage.value = '已成功绑定第三方登录 (Authentik SSO)！';
          emit('userUpdated');
        } else {
          errorMessage.value = data.detail || '绑定失败，请稍后重试';
        }
      } catch (e) {
        errorMessage.value = '网络请求异常，请稍后重试';
      } finally {
        loading.value = false;
      }
    };

    watch(() => props.visible, (val) => {
      if (val) {
        errorMessage.value = '';
        successMessage.value = '';
        fetchPasskeys();
      }
    });

    return {
      activeTab,
      loading,
      passkeys,
      newPasskeyName,
      isPasskeyLimitReached,
      errorMessage,
      successMessage,
      passwordForm,
      formatTime,
      checkPasswordUppercase,
      generatePassword,
      registerPasskey,
      deletePasskey,
      submitChangePassword,
      handleUnbindOAuth,
      handleBindOAuth
    };
  },
  template: `
    <div v-if="visible" class="fixed inset-0 z-50 overflow-y-auto flex items-center justify-center p-4">
      <div class="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity" @click="$emit('close')"></div>

      <div class="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 max-w-xl w-full p-6 md:p-8 z-10">
        <!-- 弹窗标题 -->
        <div class="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-700 mb-5">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-sky-100 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 flex items-center justify-center">
              <i class="fa-solid fa-user-shield text-lg"></i>
            </div>
            <div>
              <h3 class="text-lg font-bold text-slate-900 dark:text-white">个人安全中心</h3>
              <p class="text-xs text-slate-500 dark:text-slate-400">当前账号: <span class="font-semibold text-slate-700 dark:text-slate-200">{{ user.username }}</span> ({{ user.role === 'admin' ? '系统管理员' : '普通成员' }})</p>
            </div>
          </div>
          <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer">
            <i class="fa-solid fa-xmark text-lg"></i>
          </button>
        </div>

        <!-- 标签页切换 -->
        <div class="flex border-b border-slate-200 dark:border-slate-700 mb-5">
          <button @click="activeTab = 'passkeys'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-semibold': activeTab === 'passkeys', 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300': activeTab !== 'passkeys'}"
                  class="pb-2.5 px-3.5 text-xs sm:text-sm border-b-2 transition-all flex items-center gap-1.5 cursor-pointer">
            <i class="fa-solid fa-fingerprint"></i>
            <span>通行密钥</span>
            <span class="px-1.5 py-0.2 text-[10px] rounded-full bg-slate-100 dark:bg-slate-700 font-mono">{{ passkeys.length }}/5</span>
          </button>

          <button @click="activeTab = 'password'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-semibold': activeTab === 'password', 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300': activeTab !== 'password'}"
                  class="pb-2.5 px-3.5 text-xs sm:text-sm border-b-2 transition-all flex items-center gap-1.5 cursor-pointer">
            <i class="fa-solid fa-key"></i>
            <span>修改密码</span>
          </button>

          <button @click="activeTab = 'oauth'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-semibold': activeTab === 'oauth', 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300': activeTab !== 'oauth'}"
                  class="pb-2.5 px-3.5 text-xs sm:text-sm border-b-2 transition-all flex items-center gap-1.5 cursor-pointer">
            <i class="fa-solid fa-id-card-clip"></i>
            <span>第三方登录</span>
            <span v-if="user.oauth_provider" class="w-2 h-2 rounded-full bg-emerald-500"></span>
          </button>
        </div>

        <!-- 提示信息 -->
        <div v-if="errorMessage" class="mb-4 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
          <i class="fa-solid fa-circle-exclamation shrink-0"></i>
          <span class="flex-1 leading-relaxed">{{ errorMessage }}</span>
        </div>
        <div v-if="successMessage" class="mb-4 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs flex items-center gap-2">
          <i class="fa-solid fa-circle-check shrink-0"></i>
          <span class="flex-1 leading-relaxed">{{ successMessage }}</span>
        </div>

        <!-- 页签 1: 通行密钥绑定与列表 (最多 5 个限制 + 记录名称、创建时间、使用时间) -->
        <div v-if="activeTab === 'passkeys'" class="space-y-4">
          <!-- 绑定新通行密钥卡片 -->
          <div class="p-4 rounded-xl bg-sky-50/70 dark:bg-sky-950/30 border border-sky-100 dark:border-sky-900/40">
            <div class="flex items-center justify-between mb-2">
              <h4 class="text-xs font-bold text-sky-900 dark:text-sky-200 flex items-center gap-1.5">
                <i class="fa-solid fa-shield-halved"></i>
                <span>添加当前设备通行密钥</span>
              </h4>
              <span class="text-[11px] font-mono" :class="isPasskeyLimitReached ? 'text-rose-500 font-bold' : 'text-sky-600 dark:text-sky-400'">
                已绑定: {{ passkeys.length }} / 5 个 (上限 5 个)
              </span>
            </div>
            <p class="text-[11px] text-sky-700 dark:text-sky-400 mb-3 leading-relaxed">
              支持通过 Apple Touch ID / Face ID、Windows Hello 或 FIDO2 硬件密钥一键免密认证。
            </p>

            <div v-if="isPasskeyLimitReached" class="p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2">
              <i class="fa-solid fa-triangle-exclamation shrink-0"></i>
              <span>已达到最大配额限制 (5/5)，若需绑定新设备请先在下方解除已弃用的密钥。</span>
            </div>

            <div v-else class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <input v-model="newPasskeyName" type="text" placeholder="设置密钥名称 (例如: MacBook Pro, iPhone 16)" 
                     class="flex-1 px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500">
              <button @click="registerPasskey" :disabled="loading || isPasskeyLimitReached"
                      class="px-4 py-2 text-xs font-semibold rounded-xl bg-sky-600 hover:bg-sky-500 text-white shadow-xs transition-all flex items-center justify-center gap-1.5 shrink-0 disabled:opacity-50 cursor-pointer">
                <i v-if="loading" class="fa-solid fa-circle-notch fa-spin"></i>
                <i v-else class="fa-solid fa-plus"></i>
                <span>立即绑定当前设备</span>
              </button>
            </div>
          </div>

          <!-- 已绑定密钥详细列表 -->
          <div>
            <div class="flex items-center justify-between mb-2">
              <h5 class="text-xs font-semibold text-slate-700 dark:text-slate-300">已绑定的通行密钥列表</h5>
              <span class="text-[10px] text-slate-400">记录名称、创建时间与最后验证时间</span>
            </div>

            <div v-if="passkeys.length === 0" class="text-center py-7 text-xs text-slate-400 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">
              <i class="fa-solid fa-fingerprint text-2xl text-slate-300 dark:text-slate-600 mb-2 block"></i>
              暂未绑定通行密钥，建议点击上方按钮绑定当前设备
            </div>

            <div v-else class="divide-y divide-slate-100 dark:divide-slate-700 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
              <div v-for="pk in passkeys" :key="pk.id" class="p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors">
                <div class="flex items-start gap-3">
                  <div class="w-8 h-8 rounded-lg bg-sky-100 dark:bg-sky-950/80 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0 mt-0.5">
                    <i class="fa-solid fa-shield-halved text-sm"></i>
                  </div>
                  <div>
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-bold text-slate-800 dark:text-slate-200">{{ pk.name }}</span>
                      <span class="px-1.5 py-0.2 text-[10px] rounded bg-slate-100 dark:bg-slate-700 text-slate-500 font-mono">ID: {{ pk.credential_id }}</span>
                    </div>
                    <div class="text-[11px] text-slate-400 mt-1 space-x-3">
                      <span><i class="fa-regular fa-calendar-plus mr-1"></i>创建: {{ formatTime(pk.created_at) }}</span>
                      <span><i class="fa-regular fa-clock mr-1"></i>最后使用: {{ formatTime(pk.last_used_at) }}</span>
                      <span class="font-mono">验签: {{ pk.sign_count }}次</span>
                    </div>
                  </div>
                </div>

                <button @click="deletePasskey(pk.id, pk.name)" class="self-end sm:self-center px-2.5 py-1 text-xs text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-lg transition-all cursor-pointer">
                  <i class="fa-regular fa-trash-can mr-1"></i>解绑
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 页签 2: 修改自身密码 (20~260位，纯小写+数字+符号) -->
        <form v-else-if="activeTab === 'password'" @submit.prevent="submitChangePassword" class="space-y-4">
          <div v-if="user.has_password !== false">
            <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">当前原密码</label>
            <input v-model="passwordForm.old_password" type="password" required placeholder="请输入当前原密码"
                   class="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500">
          </div>
          <div v-else class="p-2.5 rounded-xl bg-sky-50 dark:bg-sky-950/40 border border-sky-200 dark:border-sky-800 text-sky-700 dark:text-sky-300 text-xs">
            <i class="fa-solid fa-info-circle mr-1"></i>您当前账号尚未设置过独立密码，本次提交将直接为您设置新密码。
          </div>

          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                设置新密码 <span class="text-slate-400 font-normal">(20~260位，严禁大写字母)</span>
              </label>
              <button type="button" @click="generatePassword" class="text-xs text-sky-500 hover:underline cursor-pointer">
                <i class="fa-solid fa-wand-magic-sparkles mr-0.5"></i>自动生成 32 位合规密码
              </button>
            </div>
            <input v-model="passwordForm.new_password" @input="checkPasswordUppercase(passwordForm.new_password)"
                   type="text" required placeholder="纯小写字母 + 数字 + 符号"
                   class="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-sky-500">
            <div class="flex items-center justify-between mt-1 text-[11px] text-slate-400">
              <span :class="{'text-emerald-500': passwordForm.new_password.length >= 20, 'text-rose-500': passwordForm.new_password.length > 0 && passwordForm.new_password.length < 20}">
                当前长度: {{ passwordForm.new_password.length }}/260 (至少20位)
              </span>
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">确认新密码</label>
            <input v-model="passwordForm.confirm_password" type="text" required placeholder="请再次输入新密码"
                   class="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-sky-500">
          </div>

          <button type="submit" :disabled="loading"
                  class="w-full py-2.5 px-4 rounded-xl text-xs font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-xs transition-all flex items-center justify-center gap-2 disabled:opacity-50 mt-2 cursor-pointer">
            <i v-if="loading" class="fa-solid fa-circle-notch fa-spin"></i>
            <span>{{ loading ? '正在提交...' : '确认更新密码' }}</span>
          </button>
        </form>

        <!-- 页签 3: 第三方登录绑定与解绑 (Authentik SSO) -->
        <div v-else-if="activeTab === 'oauth'" class="space-y-4">
          <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-700/30">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-blue-100 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center text-lg">
                  <i class="fa-solid fa-id-card-clip"></i>
                </div>
                <div>
                  <h4 class="text-xs font-bold text-slate-800 dark:text-slate-100">Authentik 统一身份认证</h4>
                  <p class="text-[11px] text-slate-400">单点登录 (SSO) 与集中授权网关</p>
                </div>
              </div>
              <div>
                <span v-if="user.oauth_provider" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60">
                  <i class="fa-solid fa-check text-[10px]"></i>已绑定
                </span>
                <span v-else class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 dark:bg-slate-700 text-slate-500 border border-slate-200 dark:border-slate-600">
                  未绑定
                </span>
              </div>
            </div>

            <!-- 已绑定状态 -->
            <div v-if="user.oauth_provider" class="space-y-3 pt-2 border-t border-slate-200/80 dark:border-slate-700/80">
              <div class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                当前账号已与第三方身份提供商 <span class="font-semibold text-slate-800 dark:text-slate-100 font-mono">{{ user.oauth_provider }}</span> 关联。
                关联标识: <span class="font-mono text-sky-600 dark:text-sky-400">{{ user.oauth_id || user.username }}</span>
              </div>
              <div class="flex items-center justify-between pt-1">
                <span class="text-[11px] text-slate-400">若解绑，将无法直接通过 SSO 免密进入此账号</span>
                <button @click="handleUnbindOAuth" :disabled="loading"
                        class="px-3 py-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-lg transition-all cursor-pointer disabled:opacity-50">
                  <i v-if="loading" class="fa-solid fa-circle-notch fa-spin mr-1"></i>
                  <i v-else class="fa-solid fa-link-slash mr-1"></i>解除绑定
                </button>
              </div>
            </div>

            <!-- 未绑定状态 -->
            <div v-else class="space-y-3 pt-2 border-t border-slate-200/80 dark:border-slate-700/80">
              <div class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                绑定后，您可以在登录页面直接点击“第三方登录”，通过 Authentik 单点登录直接进入当前用户。
              </div>
              <div class="flex items-center justify-end pt-1">
                <button @click="handleBindOAuth" :disabled="loading"
                        class="px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 rounded-xl shadow-xs transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
                  <i v-if="loading" class="fa-solid fa-circle-notch fa-spin"></i>
                  <i v-else class="fa-solid fa-link"></i>
                  <span>立即绑定当前 Authentik 会话</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部关闭按钮 -->
        <div class="mt-6 pt-4 border-t border-slate-200 dark:border-slate-700 flex justify-end">
          <button @click="$emit('close')" class="px-4 py-2 text-xs font-medium rounded-xl border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 transition-all cursor-pointer">
            关 闭
          </button>
        </div>
      </div>
    </div>
  `
};
