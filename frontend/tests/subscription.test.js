import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

import {
  buildClientSchemeUrl,
  buildSubscriptionUrl,
  resolveQrPayload
} from '../src/utils/subscription.js';

const ORIGIN = 'https://sub.example.com';
const TOKEN = 'a'.repeat(64);

function createQrMatrix(text, level = 'M') {
  const qrPath = path.resolve(import.meta.dirname, '../public/qrcode.min.js');
  const code = fs.readFileSync(qrPath, 'utf8');
  const ctx = {
    window: {},
    navigator: { userAgent: 'Mozilla/5.0' },
    CanvasRenderingContext2D: function () {},
    Image: function () {},
    document: {
      createElement: () => ({
        style: {},
        setAttribute: () => {},
        appendChild: () => {},
        getContext: () => ({ fillRect: () => {}, strokeRect: () => {}, clearRect: () => {} }),
        toDataURL: () => 'data:image/png;base64,'
      }),
      documentElement: { tagName: 'HTML' }
    },
    console
  };
  ctx.window = ctx;
  vm.runInNewContext(code, ctx);
  const el = { innerHTML: '', title: '', appendChild: () => {}, style: {} };
  const qr = new ctx.QRCode(el, {
    text,
    width: 180,
    height: 180,
    colorDark: '#0f172a',
    colorLight: '#ffffff',
    correctLevel: ctx.QRCode.CorrectLevel[level]
  });
  const model = qr._oQRCode;
  const count = model.getModuleCount();
  let bits = '';
  for (let r = 0; r < count; r++) {
    for (let c = 0; c < count; c++) {
      bits += model.isDark(r, c) ? '1' : '0';
    }
  }
  return bits;
}

test('buildSubscriptionUrl constructs distinct target URLs with and without token', () => {
  const clash = buildSubscriptionUrl({ origin: ORIGIN, token: TOKEN, target: 'clash', customName: '  My Node  ' });
  const singbox = buildSubscriptionUrl({ origin: ORIGIN, token: TOKEN, target: 'sing-box', customName: '  My Node  ' });
  const base64 = buildSubscriptionUrl({ origin: ORIGIN, token: TOKEN, target: 'base64', customName: '  My Node  ' });

  assert.equal(clash, `${ORIGIN}/c/${TOKEN}?target=clash&name=My+Node`);
  assert.equal(singbox, `${ORIGIN}/c/${TOKEN}?target=sing-box&name=My+Node`);
  assert.equal(base64, `${ORIGIN}/c/${TOKEN}?target=base64&name=My+Node`);
  assert.equal(new Set([clash, singbox, base64]).size, 3);

  assert.equal(
    buildSubscriptionUrl({ origin: ORIGIN, token: '', target: 'sing-box', customName: '' }),
    ''
  );
  assert.equal(
    buildClientSchemeUrl({ target: 'clash', origin: ORIGIN, token: '', customName: '', defaultTitle: 'sub-egress' }),
    null
  );
});

test('buildClientSchemeUrl locks each scheme to its matching target format', () => {
  const clashScheme = buildClientSchemeUrl({
    target: 'clash',
    origin: ORIGIN,
    token: TOKEN,
    customName: '',
    defaultTitle: 'sub-egress'
  });
  assert.ok(clashScheme.startsWith('clash://install-config?'));
  assert.ok(clashScheme.includes(encodeURIComponent(`${ORIGIN}/c/${TOKEN}?target=clash`)));
  assert.ok(clashScheme.includes('name=sub-egress'));

  const singboxScheme = buildClientSchemeUrl({
    target: 'sing-box',
    origin: ORIGIN,
    token: TOKEN,
    customName: '家庭节点',
    defaultTitle: 'sub-egress'
  });
  assert.ok(singboxScheme.startsWith('sing-box://import-remote-profile?'));
  assert.ok(singboxScheme.includes(encodeURIComponent(`${ORIGIN}/c/${TOKEN}?target=sing-box&name=${encodeURIComponent('家庭节点').replace(/%20/g, '+')}`)));
  assert.ok(singboxScheme.endsWith(`#${encodeURIComponent('家庭节点')}`));

  assert.equal(
    buildClientSchemeUrl({ target: 'base64', origin: ORIGIN, token: TOKEN, customName: '', defaultTitle: 'sub-egress' }),
    null
  );
});

test('resolveQrPayload handles url vs scheme mode and base64 fallback accurately', () => {
  const clashUrl = resolveQrPayload({ target: 'clash', qrMode: 'url', origin: ORIGIN, token: TOKEN, defaultTitle: 'sub-egress' });
  const clashScheme = resolveQrPayload({ target: 'clash', qrMode: 'scheme', origin: ORIGIN, token: TOKEN, defaultTitle: 'sub-egress' });
  assert.equal(clashUrl.mode, 'url');
  assert.equal(clashUrl.text, `${ORIGIN}/c/${TOKEN}?target=clash`);
  assert.equal(clashScheme.mode, 'scheme');
  assert.equal(clashScheme.text, clashScheme.schemeUrl);
  assert.notEqual(clashUrl.text, clashScheme.text);
  assert.notEqual(clashUrl.hint, clashScheme.hint);
  assert.equal(clashUrl.meta.supportsScheme, true);

  const sbUrl = resolveQrPayload({ target: 'sing-box', qrMode: 'url', origin: ORIGIN, token: TOKEN, defaultTitle: 'sub-egress' });
  const sbScheme = resolveQrPayload({ target: 'sing-box', qrMode: 'scheme', origin: ORIGIN, token: TOKEN, defaultTitle: 'sub-egress' });
  assert.equal(sbUrl.mode, 'url');
  assert.equal(sbUrl.text, `${ORIGIN}/c/${TOKEN}?target=sing-box`);
  assert.equal(sbScheme.mode, 'scheme');
  assert.equal(sbScheme.text, sbScheme.schemeUrl);
  assert.notEqual(sbUrl.text, sbScheme.text);
  assert.notEqual(clashScheme.text, sbScheme.text);

  const b64 = resolveQrPayload({ target: 'base64', qrMode: 'scheme', origin: ORIGIN, token: TOKEN, defaultTitle: 'sub-egress' });
  assert.equal(b64.mode, 'url');
  assert.equal(b64.schemeUrl, null);
  assert.equal(b64.text, `${ORIGIN}/c/${TOKEN}?target=base64`);
  assert.equal(b64.meta.supportsScheme, false);

  assert.equal(new Set([clashUrl.text, sbUrl.text, b64.text]).size, 3);
});

test('qrcode.min.js renders distinct valid QR matrices across all target formats and modes', () => {
  const payloads = [
    resolveQrPayload({ target: 'clash', qrMode: 'url', origin: ORIGIN, token: TOKEN, customName: '测试节点', defaultTitle: 'sub-egress' }),
    resolveQrPayload({ target: 'sing-box', qrMode: 'url', origin: ORIGIN, token: TOKEN, customName: '测试节点', defaultTitle: 'sub-egress' }),
    resolveQrPayload({ target: 'base64', qrMode: 'url', origin: ORIGIN, token: TOKEN, customName: '测试节点', defaultTitle: 'sub-egress' }),
    resolveQrPayload({ target: 'clash', qrMode: 'scheme', origin: ORIGIN, token: TOKEN, customName: '测试节点', defaultTitle: 'sub-egress' }),
    resolveQrPayload({ target: 'sing-box', qrMode: 'scheme', origin: ORIGIN, token: TOKEN, customName: '测试节点', defaultTitle: 'sub-egress' })
  ];

  const matrices = payloads.map((payload) => {
    const level = payload.mode === 'scheme' || payload.text.length > 140 ? 'L' : 'M';
    return createQrMatrix(payload.text, level);
  });

  assert.equal(new Set(matrices).size, payloads.length);
});
