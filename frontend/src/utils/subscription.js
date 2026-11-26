const TARGET_QR_META = {
  clash: {
    target: 'clash',
    label: 'Clash / Mihomo',
    formatLabel: 'YAML (Mihomo)',
    badgeClass:
      'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/70 dark:text-sky-300 dark:border-sky-800',
    supportsScheme: true,
    schemeLabel: 'clash:// 一键导入',
    importLabel: 'Clash 一键导入',
    importButtonClass:
      'bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-300 border-sky-200 dark:border-sky-800 hover:bg-sky-100 dark:hover:bg-sky-900/60',
    urlHint: '在 Clash / FlClash 客户端内使用扫一扫导入',
    schemeHint: '手机系统相机扫码，可直接唤起 Clash / FlClash 导入'
  },
  'sing-box': {
    target: 'sing-box',
    label: 'Sing-box',
    formatLabel: 'JSON (Sing-box)',
    badgeClass:
      'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800',
    supportsScheme: true,
    schemeLabel: 'sing-box:// 一键导入',
    importLabel: 'Sing-box 一键导入',
    importButtonClass:
      'bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800 hover:bg-emerald-100 dark:hover:bg-emerald-900/60',
    urlHint: '在 Sing-box 客户端内使用扫一扫导入',
    schemeHint: '手机系统相机扫码，可直接唤起 Sing-box 导入'
  },
  base64: {
    target: 'base64',
    label: 'Base64 / URI',
    formatLabel: 'TXT (Base64)',
    badgeClass:
      'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/70 dark:text-purple-300 dark:border-purple-800',
    supportsScheme: false,
    schemeLabel: '',
    importLabel: '',
    importButtonClass: '',
    urlHint: '在客户端内使用扫一扫导入 Base64 / URI 订阅链接',
    schemeHint: ''
  }
};

/**
 * Normalize subscription export target to one of clash, sing-box, or base64.
 */
export function normalizeTarget(target) {
  if (target === 'sing-box') return 'sing-box';
  if (target === 'base64') return 'base64';
  return 'clash';
}

/**
 * Build the HTTPS subscription endpoint URL for a specific target format.
 */
export function buildSubscriptionUrl({ origin, token, target, customName } = {}) {
  const normalized = normalizeTarget(target);
  const params = new URLSearchParams();
  params.append('target', normalized);
  if (customName && customName.trim()) {
    params.append('name', customName.trim());
  }
  const queryStr = params.toString();
  if (token) {
    return `${origin}/c/${token}?${queryStr}`;
  }
  return `${origin}/feed?${queryStr}`;
}

/**
 * Build the client deep-link scheme URL bound strictly to the given target format.
 */
export function buildClientSchemeUrl({ target, origin, token, customName, defaultTitle } = {}) {
  const normalized = normalizeTarget(target);
  const profileName = (customName && customName.trim()) || defaultTitle || 'sub-egress';

  if (normalized === 'clash') {
    const subUrl = buildSubscriptionUrl({ origin, token, target: 'clash', customName });
    return `clash://install-config?url=${encodeURIComponent(subUrl)}&name=${encodeURIComponent(profileName)}`;
  }

  if (normalized === 'sing-box') {
    const subUrl = buildSubscriptionUrl({ origin, token, target: 'sing-box', customName });
    return `sing-box://import-remote-profile?url=${encodeURIComponent(subUrl)}#${encodeURIComponent(profileName)}`;
  }

  return null;
}

/**
 * Return UI and QR metadata for the given target format.
 */
export function getTargetQrMeta(target) {
  return TARGET_QR_META[normalizeTarget(target)];
}

/**
 * Resolve the active QR code text, mode, hint, and import button state for a target.
 */
export function resolveQrPayload({ target, qrMode = 'url', origin, token, customName, defaultTitle } = {}) {
  const meta = getTargetQrMeta(target);
  const effectiveMode = qrMode === 'scheme' && meta.supportsScheme ? 'scheme' : 'url';
  const url = buildSubscriptionUrl({ origin, token, target: meta.target, customName });
  const schemeUrl = buildClientSchemeUrl({ target: meta.target, origin, token, customName, defaultTitle });
  const text = effectiveMode === 'scheme' && schemeUrl ? schemeUrl : url;
  const hint = effectiveMode === 'scheme' ? meta.schemeHint : meta.urlHint;
  const payloadLabel = effectiveMode === 'scheme' ? meta.schemeLabel : 'HTTPS 订阅链接';

  return {
    mode: effectiveMode,
    text,
    url,
    schemeUrl,
    hint,
    payloadLabel,
    meta
  };
}
