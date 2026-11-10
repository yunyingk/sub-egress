import { ref } from 'vue';

const modes = ['system', 'light', 'dark'];
const cacheKey = 'sub_egress_theme_mode';
const media = window.matchMedia('(prefers-color-scheme: dark)');
let cached = 'system';
try {
  cached = localStorage.getItem(cacheKey) || localStorage.getItem('sub_egress_theme') || 'system';
} catch (e) {}
export const themeMode = ref(modes.includes(cached) ? cached : 'system'); // 'light' | 'dark' | 'system'
export const themeReady = ref(false);
export const themeSaving = ref(false);
export const themeError = ref('');
let accountId = null;
let savedMode = 'system';

function applyTheme() {
  const isDark = themeMode.value === 'dark' || (themeMode.value === 'system' && media.matches);
  document.documentElement.classList.toggle('dark', isDark);
  document.documentElement.classList.toggle('light', !isDark);
}

function applyMode(mode) {
  themeMode.value = mode;
  applyTheme();
  try { localStorage.setItem(cacheKey, mode); } catch (e) {}
}

media.addEventListener('change', () => {
  if (themeMode.value === 'system') applyTheme();
});

export function syncAccountTheme(user) {
  if (!user) return;
  if (themeSaving.value && accountId === user.id) return;
  accountId = user.id;
  savedMode = modes.includes(user.theme_mode) ? user.theme_mode : 'system';
  themeReady.value = true;
  themeError.value = '';
  applyMode(savedMode);
}

export async function selectAccountTheme(mode) {
  if (!themeReady.value || themeSaving.value || !modes.includes(mode)) return;
  const requestedFor = accountId;
  themeSaving.value = true;
  themeError.value = '';
  applyMode(mode);
  try {
    const response = await fetch('/api/user/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_mode: mode }),
    });
    if (!response.ok) throw new Error('save failed');
    if (accountId === requestedFor) savedMode = mode;
  } catch (e) {
    if (accountId === requestedFor) {
      applyMode(savedMode);
      themeError.value = '外观保存失败，请重试';
    }
  } finally {
    themeSaving.value = false;
  }
}
