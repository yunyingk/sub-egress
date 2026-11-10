<template>
    <div class="relative theme-toggle-container">
      <button @click.stop="toggleDropdown" 
              type="button"
              class="px-3 py-2 text-sm font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 shadow-xs transition-all flex items-center gap-2"
              :title="'当前外观: ' + (themeMode === 'light' ? '浅色' : themeMode === 'dark' ? '深色' : '跟随系统')">
        <i v-if="themeMode === 'light'" class="fa-solid fa-sun text-amber-500 text-sm"></i>
        <i v-else-if="themeMode === 'dark'" class="fa-solid fa-moon text-sky-400 text-sm"></i>
        <i v-else class="fa-solid fa-desktop text-slate-500 dark:text-slate-400 text-sm"></i>
        
        <span class="text-xs">
          {{ themeMode === 'light' ? '浅色' : (themeMode === 'dark' ? '深色' : '跟随系统') }}
        </span>
        <i class="fa-solid fa-chevron-down text-[10px] text-slate-400 transition-transform duration-200"
           :class="{'rotate-180': isOpen}"></i>
      </button>

      <!-- 三选一下拉菜单 (浅色 / 深色 / 跟随系统) -->
      <div v-show="isOpen" 
           class="absolute right-0 mt-1.5 w-36 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl py-1.5 z-50 text-xs font-medium text-slate-700 dark:text-slate-200 space-y-0.5">
        
        <button @click="selectTheme('light')" 
                type="button"
                class="w-full px-3 py-2 flex items-center justify-between hover:bg-slate-100 dark:hover:bg-slate-700/60 transition text-left"
                :class="{'text-sky-600 dark:text-sky-400 font-bold bg-sky-50/50 dark:bg-sky-950/30': themeMode === 'light'}">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-sun text-amber-500 w-4 text-center"></i>
            <span>浅色模式</span>
          </div>
          <i v-if="themeMode === 'light'" class="fa-solid fa-check text-sky-600 dark:text-sky-400 text-xs"></i>
        </button>

        <button @click="selectTheme('dark')" 
                type="button"
                class="w-full px-3 py-2 flex items-center justify-between hover:bg-slate-100 dark:hover:bg-slate-700/60 transition text-left"
                :class="{'text-sky-600 dark:text-sky-400 font-bold bg-sky-50/50 dark:bg-sky-950/30': themeMode === 'dark'}">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-moon text-sky-400 w-4 text-center"></i>
            <span>深色模式</span>
          </div>
          <i v-if="themeMode === 'dark'" class="fa-solid fa-check text-sky-600 dark:text-sky-400 text-xs"></i>
        </button>

        <button @click="selectTheme('system')" 
                type="button"
                class="w-full px-3 py-2 flex items-center justify-between hover:bg-slate-100 dark:hover:bg-slate-700/60 transition text-left"
                :class="{'text-sky-600 dark:text-sky-400 font-bold bg-sky-50/50 dark:bg-sky-950/30': themeMode === 'system'}">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-desktop text-slate-500 dark:text-slate-400 w-4 text-center"></i>
            <span>跟随系统</span>
          </div>
          <i v-if="themeMode === 'system'" class="fa-solid fa-check text-sky-600 dark:text-sky-400 text-xs"></i>
        </button>

      </div>
    </div>
  
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue';

export default {
  name: 'ThemeToggle',
  setup() {
    const isOpen = ref(false);
    const themeMode = ref('system'); // 'light' | 'dark' | 'system'
    const systemPrefersDark = ref(false);

    let mediaQuery = null;

    const updateSystemPreference = (e) => {
      systemPrefersDark.value = e.matches;
      if (themeMode.value === 'system') {
        applyTheme();
      }
    };

    const applyTheme = () => {
      let isDark = false;
      if (themeMode.value === 'dark') {
        isDark = true;
      } else if (themeMode.value === 'light') {
        isDark = false;
      } else {
        isDark = systemPrefersDark.value;
      }

      if (isDark) {
        document.documentElement.classList.add('dark');
        document.documentElement.classList.remove('light');
      } else {
        document.documentElement.classList.remove('dark');
        document.documentElement.classList.add('light');
      }
    };

    const selectTheme = (mode) => {
      themeMode.value = mode;
      localStorage.setItem('sub_egress_theme_mode', mode);
      applyTheme();
      isOpen.value = false;
    };

    const toggleDropdown = () => {
      isOpen.value = !isOpen.value;
    };

    const handleClickOutside = (e) => {
      if (isOpen.value && !e.target.closest('.theme-toggle-container')) {
        isOpen.value = false;
      }
    };

    onMounted(() => {
      mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      systemPrefersDark.value = mediaQuery.matches;
      mediaQuery.addEventListener('change', updateSystemPreference);

      const saved = localStorage.getItem('sub_egress_theme_mode') || localStorage.getItem('sub_egress_theme') || 'system';
      themeMode.value = ['light', 'dark', 'system'].includes(saved) ? saved : 'system';
      applyTheme();

      document.addEventListener('click', handleClickOutside);
    });

    onUnmounted(() => {
      if (mediaQuery) {
        mediaQuery.removeEventListener('change', updateSystemPreference);
      }
      document.removeEventListener('click', handleClickOutside);
    });

    return {
      isOpen,
      themeMode,
      selectTheme,
      toggleDropdown
    };
  }
};
</script>
