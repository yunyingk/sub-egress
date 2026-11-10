import assert from 'node:assert/strict';
import test from 'node:test';

const storage = new Map([['sub_egress_theme_mode', 'light']]);
globalThis.localStorage = { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) };
const classes = new Set();
globalThis.document = { createElement: () => ({}), documentElement: { classList: { toggle: (name, on) => on ? classes.add(name) : classes.delete(name) } } };
let systemChange;
const media = { matches: false, addEventListener: (_, cb) => { systemChange = cb; } };
globalThis.window = { matchMedia: () => media };
const theme = await import('../src/theme.js');

test('account settings override local cache, save, rollback, and follow system', async () => {
  theme.syncAccountTheme({ id: 1, theme_mode: 'dark' });
  assert.equal(theme.themeMode.value, 'dark');
  assert.ok(classes.has('dark'));
  assert.equal(storage.get('sub_egress_theme_mode'), 'dark');
  globalThis.fetch = async (_, request) => {
    assert.deepEqual(JSON.parse(request.body), { theme_mode: 'light' });
    return { ok: true };
  };
  await theme.selectAccountTheme('light');
  assert.equal(theme.themeMode.value, 'light');
  globalThis.fetch = async () => ({ ok: false });
  await theme.selectAccountTheme('dark');
  assert.equal(theme.themeMode.value, 'light');
  assert.ok(theme.themeError.value);
  theme.syncAccountTheme({ id: 2, theme_mode: 'system' });
  assert.equal(theme.themeMode.value, 'system');
  media.matches = true;
  systemChange();
  assert.ok(classes.has('dark'));
  media.matches = false;
  systemChange();
  assert.ok(classes.has('light'));
});
