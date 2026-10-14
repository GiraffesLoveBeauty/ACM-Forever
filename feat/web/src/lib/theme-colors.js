const MAX_JSON_BYTES = 32768;
const BASE_KEYS = ['primary', 'background', 'surface', 'accent'];
const OVERRIDE_KEYS = ['text', 'muted', 'border', 'link', 'selected', 'hero'];
const MODES = ['light', 'dark', 'system'];
const LABELS = {
  primary: '主色',
  background: '页面背景',
  surface: '卡片背景',
  accent: '强调色',
  text: '正文',
  muted: '次要文字',
  border: '边框',
  link: '链接',
  selected: '选中项文字',
  hero: '欢迎横幅背景',
};
const OVERRIDE_TOKENS = {
  text: '--text',
  muted: '--muted',
  border: '--line',
  link: '--link',
  selected: '--selected-fg',
  hero: '--hero-bg',
};
const clone = (value) => JSON.parse(JSON.stringify(value));
const luminanceCache = new Map(),
  tokenCache = new Map(),
  readableCache = new Map(),
  candidateCache = new Map();
// 8-bit sRGB has only 256 channel values. Avoid repeated exponentiation and
// keep hot entries instead of periodically clearing all caches during a drag.
const linearChannels = Array.from({ length: 256 }, (_, n) => {
  const c = n / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
});
function cachePut(cache, key, value, limit) {
  if (cache.size >= limit) cache.delete(cache.keys().next().value);
  cache.set(key, value);
  return value;
}

function normalizeColor(value) {
  if (typeof value !== 'string') return null;
  const color = value.trim();
  if (/^#[0-9a-f]{3}$/i.test(color))
    return (
      '#' +
      color
        .slice(1)
        .split('')
        .map((c) => c + c)
        .join('')
        .toLowerCase()
    );
  return /^#[0-9a-f]{6}$/i.test(color) ? color.toLowerCase() : null;
}
function colorValue(value) {
  const color = normalizeColor(value);
  if (!color) throw new TypeError('颜色只接受 #RGB 或 #RRGGBB');
  return color;
}
function rgb(value) {
  const color = colorValue(value);
  return [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
}
function hex(parts) {
  return (
    '#' +
    parts
      .map((n) =>
        Math.max(0, Math.min(255, Math.round(n)))
          .toString(16)
          .padStart(2, '0'),
      )
      .join('')
  );
}
function mix(a, b, amount) {
  const first = rgb(a),
    second = rgb(b);
  return hex(first.map((n, i) => n * (1 - amount) + second[i] * amount));
}
function luminance(color) {
  const key = colorValue(color);
  if (luminanceCache.has(key)) return luminanceCache.get(key);
  const packed = parseInt(key.slice(1), 16);
  const result =
    linearChannels[packed >>> 16] * 0.2126 +
    linearChannels[(packed >>> 8) & 255] * 0.7152 +
    linearChannels[packed & 255] * 0.0722;
  return cachePut(luminanceCache, key, result, 4096);
}
function getContrast(first, second) {
  const a = luminance(first),
    b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
// Find an AA foreground, retaining the user's hue when possible. Opposite
// surfaces may have no common safe color; report that instead of claiming AA.
function readable(backgrounds, preferred, minimum = 4.5) {
  const key = backgrounds.join(',') + '|' + preferred + '|' + minimum;
  if (readableCache.has(key)) {
    const result = readableCache.get(key);
    readableCache.delete(key);
    readableCache.set(key, result);
    return result;
  }
  return cachePut(readableCache, key, solveReadable(backgrounds, preferred, minimum), 512);
}
function solveReadable(backgrounds, preferred, minimum) {
  const target = colorValue(preferred),
    targetRgb = rgb(target);
  const levels = backgrounds.map((bg) => luminance(bg));
  const ratioOf = (color) => {
    const value = luminance(color);
    let ratio = Infinity;
    for (const level of levels)
      ratio = Math.min(ratio, (Math.max(value, level) + 0.05) / (Math.min(value, level) + 0.05));
    return ratio;
  };
  if (ratioOf(target) >= minimum) return target;
  let intervals = [[0, 1]];
  for (const level of levels) {
    const next = [],
      lower = (level + 0.05) / minimum - 0.05,
      upper = minimum * (level + 0.05) - 0.05;
    for (const [lo, hi] of intervals) {
      if (lo <= Math.min(hi, lower)) next.push([lo, Math.min(hi, lower)]);
      if (Math.max(lo, upper) <= hi) next.push([Math.max(lo, upper), hi]);
    }
    intervals = next;
  }
  let safe = null,
    distance = Infinity,
    best = '#000000',
    bestRatio = -1;
  const consider = (candidate) => {
    const ratio = ratioOf(candidate);
    if (ratio > bestRatio) {
      best = candidate;
      bestRatio = ratio;
    }
    if (ratio >= minimum) {
      const d = rgb(candidate).reduce((sum, n, i) => sum + (n - targetRgb[i]) ** 2, 0);
      if (d < distance) {
        safe = candidate;
        distance = d;
      }
    }
  };
  // Monotone RGB paths: locate a safe boundary instead of scanning every shade.
  const pathEdge = (from, to, threshold, lastBelow) => {
    const at = (t) => hex(from.map((n, i) => n * (1 - t) + to[i] * t));
    let lo = 0,
      hi = 1;
    for (let i = 0; i < 18; i++) {
      const mid = (lo + hi) / 2,
        value = luminance(at(mid));
      if (lastBelow ? value <= threshold : value < threshold) lo = mid;
      else hi = mid;
    }
    consider(at(lastBelow ? lo : hi));
  };
  for (const [lo, hi] of intervals) {
    pathEdge([0, 0, 0], targetRgb, hi, true);
    pathEdge(targetRgb, [255, 255, 255], lo, false);
    let left = 0,
      right = 256;
    while (left < right) {
      const mid = (left + right) >>> 1;
      if (luminance(hex([mid, mid, mid])) < lo) left = mid + 1;
      else right = mid;
    }
    const low = left;
    left = 0;
    right = 256;
    while (left < right) {
      const mid = (left + right) >>> 1;
      if (luminance(hex([mid, mid, mid])) <= hi) left = mid + 1;
      else right = mid;
    }
    const high = left - 1;
    if (low <= high && low <= 255 && high >= 0) {
      const gray = Math.max(
        low,
        Math.min(high, Math.round((targetRgb[0] + targetRgb[1] + targetRgb[2]) / 3)),
      );
      consider(hex([gray, gray, gray]));
    }
  }
  if (safe) return safe;
  // Preserve exact best-effort fallback for incompatible or discrete backgrounds.
  best = '#000000';
  bestRatio = -1;
  let candidates = candidateCache.get(target);
  if (!candidates) {
    const colors = new Set([target, '#000000', '#ffffff']);
    for (let i = 0; i <= 50; i++) {
      colors.add(mix(target, '#000000', i / 50));
      colors.add(mix(target, '#ffffff', i / 50));
    }
    for (let n = 0; n <= 255; n++) colors.add(hex([n, n, n]));
    candidates = Array.from(colors, (color) => ({
      color,
      level: luminance(color),
      distance: rgb(color).reduce((sum, n, i) => sum + (n - targetRgb[i]) ** 2, 0),
    }));
    cachePut(candidateCache, target, candidates, 32);
  }
  for (const candidate of candidates) {
    let ratio = Infinity;
    for (const level of levels)
      ratio = Math.min(
        ratio,
        (Math.max(candidate.level, level) + 0.05) / (Math.min(candidate.level, level) + 0.05),
      );
    if (ratio > bestRatio) {
      best = candidate.color;
      bestRatio = ratio;
    }
    if (ratio >= minimum && candidate.distance < distance) {
      safe = candidate.color;
      distance = candidate.distance;
    }
  }
  return safe || best;
}
function createDefaultTheme() {
  return {
    version: 1,
    mode: 'system',
    light: {
      colors: { primary: '#292c29', background: '#e8e9e4', surface: '#f8f8f3', accent: '#f1f547' },
      overrides: {
        text: '#292c29',
        muted: '#62685e',
        border: '#c7cabc',
        link: '#292c29',
        selected: '#292c29',
        hero: '#20231f',
      },
    },
    dark: {
      colors: { primary: '#e2e5d8', background: '#1a1d19', surface: '#242823', accent: '#f1f547' },
      overrides: {
        text: '#f5f6eb',
        muted: '#b4bbac',
        border: '#454b41',
        link: '#eef1df',
        selected: '#eef1df',
        hero: '#151814',
      },
    },
  };
}
// Legacy color families are optional starting points, never storage migrations.
const PRESETS = Object.freeze(
  [
    {
      id: 'industrial',
      name: '工业黄',
      light: ['#292c29', '#e8e9e4', '#f8f8f3', '#f1f547'],
      dark: ['#e2e5d8', '#1a1d19', '#242823', '#f1f547'],
    },
    {
      id: 'mint',
      name: '清绿',
      light: ['#16766a', '#edf3ef', '#fbfdf9', '#efcf63'],
      dark: ['#70c3a6', '#122222', '#1a302e', '#edcb69'],
    },
    {
      id: 'gray',
      name: '白灰',
      light: ['#68717a', '#f0f1f3', '#fcfcfd', '#aab1b9'],
      dark: ['#c0c6cd', '#202327', '#292d32', '#c9cdd2'],
    },
    {
      id: 'sunshine',
      name: '暖黄',
      light: ['#98741f', '#faf5e6', '#fffdf6', '#edc54d'],
      dark: ['#e6c65e', '#272317', '#342e1e', '#f2cf60'],
    },
    {
      id: 'rose',
      name: '柔粉',
      light: ['#b45178', '#faf0f4', '#fffafd', '#f0c4af'],
      dark: ['#e39ab8', '#281e24', '#352730', '#f0c4af'],
    },
  ].map((item) =>
    Object.freeze({ ...item, light: Object.freeze(item.light), dark: Object.freeze(item.dark) }),
  ),
);
function presetProfile(id, mode) {
  const preset = PRESETS.find((item) => item.id === id);
  if (!preset || !['light', 'dark'].includes(mode)) throw new TypeError('未知预设或模式');
  return {
    colors: Object.fromEntries(BASE_KEYS.map((key, index) => [key, preset[mode][index]])),
    overrides: id === 'industrial' ? createDefaultTheme()[mode].overrides : {},
  };
}
// Validate descriptors before reading values; reject unknown keys, getters,
// symbols and custom prototypes. Ordinary records from other realms are OK.
function record(value, allowed, required, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new TypeError(label + ' 必须是对象');
  const proto = Object.getPrototypeOf(value);
  if (proto !== null && proto !== Object.prototype) {
    const constructor = Object.getOwnPropertyDescriptor(proto, 'constructor');
    if (
      Object.getPrototypeOf(proto) !== null ||
      !constructor ||
      !('value' in constructor) ||
      typeof constructor.value !== 'function' ||
      constructor.value.prototype !== proto ||
      Function.prototype.toString.call(constructor.value) !== 'function Object() { [native code] }'
    ) {
      throw new TypeError(label + ' 不接受自定义原型');
    }
  }
  const descriptors = Object.getOwnPropertyDescriptors(value),
    output = Object.create(null);
  for (const key of Reflect.ownKeys(descriptors)) {
    if (typeof key !== 'string' || !allowed.includes(key))
      throw new TypeError(label + ' 含未知字段');
    const descriptor = descriptors[key];
    if (!('value' in descriptor) || !descriptor.enumerable)
      throw new TypeError(label + ' 不接受访问器或隐藏字段');
    output[key] = descriptor.value;
  }
  for (const key of required)
    if (!Object.prototype.hasOwnProperty.call(output, key))
      throw new TypeError(label + ' 缺少 ' + key);
  return output;
}
function validateProfile(value, label) {
  const profile = record(value, ['colors', 'overrides'], ['colors', 'overrides'], label);
  const colors = record(profile.colors, BASE_KEYS, BASE_KEYS, label + '.colors');
  const overrides = record(profile.overrides, OVERRIDE_KEYS, [], label + '.overrides');
  const result = { colors: {}, overrides: {} };
  BASE_KEYS.forEach((key) => {
    result.colors[key] = colorValue(colors[key]);
  });
  Object.keys(overrides).forEach((key) => {
    result.overrides[key] = colorValue(overrides[key]);
  });
  return result;
}
function utf8Length(text) {
  let count = 0;
  for (const character of text) {
    const code = character.codePointAt(0);
    count += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
  }
  return count;
}
function parseThemeJSON(text) {
  if (typeof text !== 'string' || utf8Length(text) > MAX_JSON_BYTES)
    throw new TypeError('主题 JSON 不得超过 32768 字节');
  return validateTheme(JSON.parse(text));
}
function validateTheme(value) {
  if (typeof value === 'string') return parseThemeJSON(value);
  const theme = record(
    value,
    ['version', 'mode', 'light', 'dark'],
    ['version', 'mode', 'light', 'dark'],
    '主题',
  );
  if (theme.version !== 1 || !MODES.includes(theme.mode))
    throw new TypeError('不支持的主题版本或模式');
  return {
    version: 1,
    mode: theme.mode,
    light: validateProfile(theme.light, 'light'),
    dark: validateProfile(theme.dark, 'dark'),
  };
}
function deriveTokens(value, dark) {
  const profile = validateProfile(value, 'profile'),
    cacheKey = JSON.stringify([profile, !!dark]);
  if (tokenCache.has(cacheKey)) return tokenCache.get(cacheKey);
  const c = profile.colors,
    o = profile.overrides,
    backgrounds = [c.background, c.surface];
  const text = o.text || readable(backgrounds, dark ? '#edf5eb' : '#163432');
  const muted = o.muted || readable(backgrounds, mix(text, c.surface, 0.3));
  const subtle = mix(c.surface, c.primary, 0.1);
  const hero = o.hero || mix(c.surface, c.primary, dark ? 0.1 : 0.15);
  const art = mix(c.primary, '#101820', 0.75),
    artBack = c.accent;
  const tokens = {
    '--bg': c.background,
    '--panel': c.surface,
    '--panel-raised': c.surface,
    '--text': text,
    '--muted': muted,
    '--line': o.border || mix(c.surface, text, 0.22),
    '--brand': c.primary,
    '--brand-strong': c.primary,
    '--brand2': c.accent,
    '--accent': c.accent,
    '--accent-blue': readable(backgrounds, '#6679df'),
    '--accent-coral': readable(backgrounds, '#df7759'),
    '--on-brand': readable([c.primary], '#ffffff'),
    '--on-accent': readable([c.accent], '#163432'),
    '--subtle-bg': subtle,
    '--selected-fg': o.selected || readable([subtle], c.primary),
    '--hover-bg': mix(c.surface, c.primary, 0.06),
    '--link': o.link || readable(backgrounds, c.primary),
    '--focus-ring': readable(backgrounds, c.primary, 3),
    '--wash-a': c.accent + '18',
    '--wash-b': c.primary + '0c',
    '--page-backdrop': c.background,
    '--hero-bg': hero,
    '--hero-gradient': 'linear-gradient(120deg,' + hero + ',' + hero + ')',
    '--hero-text': readable([hero], '#ffffff'),
    '--hero-muted': readable([hero], mix('#ffffff', hero, 0.25)),
    '--art-shade': art,
    '--art-background': art,
    '--art-hue': '0deg',
    '--art-saturation': '1',
    '--art-label': readable([art], '#eaf3de'),
    '--art-route': readable([art], c.accent),
    '--art-node': c.accent,
    '--art-node-text': readable([c.accent, artBack], '#163432'),
    '--art-node-back': artBack,
    '--art-edge': readable([art], mix(c.accent, '#ffffff', 0.35), 3),
    '--code-bg': mix(c.surface, c.background, 0.5),
    '--shadow': dark ? '0 18px 42px rgba(0,0,0,.24)' : '0 16px 38px rgba(0,0,0,.1)',
  };
  tokens['--code-text'] = readable([tokens['--code-bg']], text);
  for (const [name, color] of [
    ['success', '#17834b'],
    ['warning', '#a66b00'],
    ['danger', '#c73545'],
    ['info', '#3478c9'],
  ]) {
    const background = mix(c.surface, color, 0.12);
    tokens['--' + name + '-bg'] = background;
    tokens['--' + name] = readable([background, c.surface, c.background], color);
  }
  return cachePut(tokenCache, cacheKey, Object.freeze(tokens), 80);
}
function contrastChecks(profile, dark) {
  return checksFromTokens(deriveTokens(profile, dark));
}
function checksFromTokens(t) {
  const checks = [];
  const add = (label, foreground, background, minimum = 4.5) => {
    const ratio = getContrast(t[foreground], t[background]);
    checks.push({ label, foreground, background, ratio, minimum, pass: ratio >= minimum });
  };
  for (const [name, token] of [
    ['正文', '--text'],
    ['次要文字', '--muted'],
    ['链接', '--link'],
  ]) {
    add(name + ' / 页面', token, '--bg');
    add(name + ' / 卡片', token, '--panel');
  }
  add('选中项', '--selected-fg', '--subtle-bg');
  add('主色按钮', '--on-brand', '--brand-strong');
  add('强调色按钮', '--on-accent', '--accent');
  add('横幅正文', '--hero-text', '--hero-bg');
  add('横幅说明', '--hero-muted', '--hero-bg');
  add('图谱标签', '--art-label', '--art-shade');
  add('图谱节点', '--art-node-text', '--art-node');
  add('图谱背面节点', '--art-node-text', '--art-node-back');
  add('代码', '--code-text', '--code-bg');
  return checks;
}
function repairProfile(value, dark) {
  const profile = validateProfile(value, 'profile');
  const backgrounds = [profile.colors.background, profile.colors.surface];
  const candidate = readable(backgrounds, dark ? '#ffffff' : '#000000');
  if (backgrounds.some((bg) => getContrast(candidate, bg) < 4.5))
    profile.colors.surface = profile.colors.background;
  for (const key of ['text', 'muted', 'link', 'selected']) delete profile.overrides[key];
  if (contrastChecks(profile, dark).some((check) => !check.pass))
    throw new Error('无法修复已检查的颜色对，请调整基础色');
  return profile;
}

export {
  BASE_KEYS,
  OVERRIDE_KEYS,
  LABELS,
  PRESETS,
  createDefaultTheme,
  presetProfile,
  deriveTokens,
  normalizeColor,
  validateTheme,
  parseThemeJSON,
  contrastChecks,
  repairProfile,
};
