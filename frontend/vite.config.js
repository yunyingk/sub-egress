import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
import { readFileSync } from 'node:fs';

const projectMetadata = readFileSync(new URL('../pyproject.toml', import.meta.url), 'utf8');
const appVersion = projectMetadata.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
if (!appVersion) throw new Error('Unable to read project version from pyproject.toml');

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(appVersion) },
  build: {
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL('./index.html', import.meta.url)),
        login: fileURLToPath(new URL('./login.html', import.meta.url)),
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/outpost.goauthentik.io': 'http://127.0.0.1:8000',
    },
  },
});
