import { ref, reactive, watch } from 'vue';

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

export default {
  name: 'UserSecurityModal',
  props: {
    visible: { type: Boolean, default: false },
    user: { type: Object, default: () => ({}) }
  },
  emits: ['close', 'userUpdated'],
  setup(props, { emit }) {
    const activeTab = ref('passkeys');
    const loading = ref(false);
    const passkeys = ref([]);
    const newPasskeyName = ref('');
    const errorMessage = ref('');
    const successMessage = ref('');

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

    // 绑定当前设备的新通行密钥 (Touch ID / Face ID / Windows Hello)
    const registerPasskey = async () => {
      errorMessage.value = '';
      successMessage.value = '';

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
    const deletePasskey = async (id) => {
      if (!confirm('确定要解绑该通行密钥吗？解绑后将无法使用该设备免密登录。')) return;
      try {
        const res = await fetch(`/api/user/passkeys/${id}`, { method: 'DELETE' });
        if (res.ok) {
          await fetchPasskeys();
          emit('userUpdated');
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
        errorMessage.value = '新密码严禁包含大写字母！';
        return;
      }
      if (passwordForm.new_password.length < 20) {
        errorMessage.value = '密码长度至少需要 20 位！';
        return;
      }

      loading.value = true;
      try {
        const res = await fetch('/api/auth/change-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            old_password: passwordForm.old_password,
            new_password: passwordForm.new_password
          })
        });
        const data = await res.json();
        if (res.ok) {
          successMessage.value = '密码修改成功！请牢记您的新密码。';
          passwordForm.old_password = '';
          passwordForm.new_password = '';
          passwordForm.confirm_password = '';
        } else {
          errorMessage.value = data.detail || '修改密码失败';
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
      errorMessage,
      successMessage,
      passwordForm,
      checkPasswordUppercase,
      generatePassword,
      registerPasskey,
      deletePasskey,
      submitChangePassword
    };
  },
  template: `
    <div v-if="visible" class="fixed inset-0 z-50 overflow-y-auto flex items-center justify-center p-4">
      <div class="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity" @click="$emit('close')"></div>

      <div class="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 max-w-xl w-full p-6 md:p-8 z-10">
        <!-- 弹窗标题 -->
        <div class="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-700 mb-6">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-sky-100 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 flex items-center justify-center">
              <i class="fa-solid fa-user-shield text-lg"></i>
            </div>
            <div>
              <h3 class="text-lg font-bold text-slate-900 dark:text-white">个人安全中心</h3>
              <p class="text-xs text-slate-500 dark:text-slate-400">当前账号: <span class="font-semibold text-slate-700 dark:text-slate-200">{{ user.username }}</span> ({{ user.role === 'admin' ? '系统管理员' : '普通成员' }})</p>
            </div>
          </div>
          <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <i class="fa-solid fa-xmark text-lg"></i>
          </button>
        </div>

        <!-- 标签页切换 -->
        <div class="flex border-b border-slate-200 dark:border-slate-700 mb-5">
          <button @click="activeTab = 'passkeys'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-semibold': activeTab === 'passkeys', 'border-transparent text-slate-500': activeTab !== 'passkeys'}"
                  class="pb-2.5 px-4 text-sm border-b-2 transition-all flex items-center gap-2">
            <i class="fa-solid fa-fingerprint"></i>
            <span>通行密钥 (Passkey)</span>
            <span class="px-1.5 py-0.2 text-[10px] rounded-full bg-slate-100 dark:bg-slate-700">{{ passkeys.length }}</span>
          </button>
          <button @click="activeTab = 'password'" 
                  :class="{'border-sky-500 text-sky-600 dark:text-sky-400 font-semibold': activeTab === 'password', 'border-transparent text-slate-500': activeTab !== 'password'}"
                  class="pb-2.5 px-4 text-sm border-b-2 transition-all flex items-center gap-2">
            <i class="fa-solid fa-key"></i>
            <span>修改密码</span>
          </button>
        </div>

        <!-- 提示信息 -->
        <div v-if="errorMessage" class="mb-4 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
          <i class="fa-solid fa-circle-exclamation shrink-0"></i>
          <span class="flex-1">{{ errorMessage }}</span>
        </div>
        <div v-if="successMessage" class="mb-4 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs flex items-center gap-2">
          <i class="fa-solid fa-circle-check shrink-0"></i>
          <span class="flex-1">{{ successMessage }}</span>
        </div>

        <!-- 页签 1: 通行密钥绑定与列表 -->
        <div v-if="activeTab === 'passkeys'" class="space-y-4">
          <div class="p-4 rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-100 dark:border-sky-900/40 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h4 class="text-xs font-bold text-sky-900 dark:text-sky-200">绑定当前设备通行密钥</h4>
              <p class="text-[11px] text-sky-700 dark:text-sky-400 mt-0.5">绑定后即可在登录页使用指纹/面容/安全密钥一键免密进入</p>
            </div>
            <div class="flex items-center gap-2">
              <input v-model="newPasskeyName" type="text" placeholder="设备备注 (例如: Mac 15)" 
                     class="px-2.5 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700">
              <button @click="registerPasskey" :disabled="loading"
                      class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white shadow-xs transition-all flex items-center gap-1.5 shrink-0 disabled:opacity-50">
                <i v-if="loading" class="fa-solid fa-circle-notch fa-spin"></i>
                <i v-else class="fa-solid fa-plus"></i>
                <span>立即绑定</span>
              </button>
            </div>
          </div>

          <!-- 已绑定密钥列表 -->
          <div>
            <h5 class="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">已绑定的通行密钥列表</h5>
            <div v-if="passkeys.length === 0" class="text-center py-6 text-xs text-slate-400 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">
              暂未绑定通行密钥，建议点击上方按钮绑定当前设备
            </div>
            <div v-else class="divide-y divide-slate-100 dark:divide-slate-700 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
              <div v-for="pk in passkeys" :key="pk.id" class="p-3 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-750">
                <div class="flex items-center gap-3">
                  <i class="fa-solid fa-shield-halved text-sky-500 text-base"></i>
                  <div>
                    <div class="text-xs font-bold text-slate-800 dark:text-slate-200">{{ pk.name }}</div>
                    <div class="text-[10px] text-slate-400 font-mono">凭证: {{ pk.credential_id }} · 登录次数: {{ pk.sign_count }}</div>
                  </div>
                </div>
                <button @click="deletePasskey(pk.id)" class="px-2 py-1 text-xs text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-md transition-all">
                  <i class="fa-regular fa-trash-can mr-1"></i>解绑
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 页签 2: 修改密码 -->
        <form v-else-if="activeTab === 'password'" @submit.prevent="submitChangePassword" class="space-y-4">
          <div>
            <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">当前原密码</label>
            <input v-model="passwordForm.old_password" type="password" required placeholder="请输入当前旧密码"
                   class="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100">
          </div>

          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                新密码 <span class="text-slate-400 font-normal">(20~260位，严禁大写字母)</span>
              </label>
              <button type="button" @click="generatePassword" class="text-xs text-sky-500 hover:underline">
                <i class="fa-solid fa-wand-magic-sparkles mr-0.5"></i>自动生成 32 位合规密码
              </button>
            </div>
            <input v-model="passwordForm.new_password" @input="checkPasswordUppercase(passwordForm.new_password)"
                   type="text" required placeholder="小写字母 + 数字 + 符号"
                   class="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 font-mono text-xs">
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">确认新密码</label>
            <input v-model="passwordForm.confirm_password" type="text" required placeholder="请再次输入新密码"
                   class="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 font-mono text-xs">
          </div>

          <button type="submit" :disabled="loading"
                  class="w-full py-2.5 px-4 rounded-xl text-xs font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-xs transition-all flex items-center justify-center gap-2 disabled:opacity-50 mt-2">
            <i v-if="loading" class="fa-solid fa-circle-notch fa-spin"></i>
            <span>{{ loading ? '正在提交...' : '确认修改密码' }}</span>
          </button>
        </form>

        <!-- 底部关闭按钮 -->
        <div class="mt-6 pt-4 border-t border-slate-200 dark:border-slate-700 flex justify-end">
          <button @click="$emit('close')" class="px-4 py-2 text-xs font-medium rounded-xl border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 transition-all">
            关 闭
          </button>
        </div>
      </div>
    </div>
  `
};
