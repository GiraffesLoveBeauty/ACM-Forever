/* ACM Forever: browser-local custom themes, explicit drafts and safe RGB tokens. */
(function (window) {
  'use strict';
  const document = window.document;
  const THEME_KEY = 'acm.theme.v1', LIBRARY_KEY = 'acm.theme.library.v1';
  const MAX_JSON_BYTES = 32768;
  const BASE_KEYS = ['primary', 'background', 'surface', 'accent'];
  const OVERRIDE_KEYS = ['text', 'muted', 'border', 'link', 'selected', 'hero'];
  const MODES = ['light', 'dark', 'system'];
  const LABELS = {primary:'主色', background:'页面背景', surface:'卡片背景', accent:'强调色', text:'正文', muted:'次要文字', border:'边框', link:'链接', selected:'选中项文字', hero:'欢迎横幅背景'};
  const OVERRIDE_TOKENS = {text:'--text', muted:'--muted', border:'--line', link:'--link', selected:'--selected-fg', hero:'--hero-bg'};
  const clone = value => JSON.parse(JSON.stringify(value));
  const luminanceCache = new Map(), tokenCache = new Map();

  function normalizeColor(value) {
    if (typeof value !== 'string') return null;
    const color = value.trim();
    if (/^#[0-9a-f]{3}$/i.test(color)) return '#' + color.slice(1).split('').map(c => c + c).join('').toLowerCase();
    return /^#[0-9a-f]{6}$/i.test(color) ? color.toLowerCase() : null;
  }
  function colorValue(value) {
    const color = normalizeColor(value);
    if (!color) throw new TypeError('颜色只接受 #RGB 或 #RRGGBB');
    return color;
  }
  function rgb(value) {
    const color = colorValue(value);
    return [1,3,5].map(i => parseInt(color.slice(i, i + 2), 16));
  }
  function hex(parts) {
    return '#' + parts.map(n => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0')).join('');
  }
  function mix(a, b, amount) {
    const first = rgb(a), second = rgb(b);
    return hex(first.map((n, i) => n * (1 - amount) + second[i] * amount));
  }
  function luminance(color) {
    const key = colorValue(color);
    if (luminanceCache.has(key)) return luminanceCache.get(key);
    const linear = rgb(key).map(n => {
      const c = n / 255;
      return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
    });
    const result = linear[0] * .2126 + linear[1] * .7152 + linear[2] * .0722;
    if (luminanceCache.size > 4096) luminanceCache.clear();
    luminanceCache.set(key, result);
    return result;
  }
  function getContrast(first, second) {
    const a = luminance(first), b = luminance(second);
    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
  }
  // Find an AA foreground, retaining the user's hue when possible. Opposite
  // surfaces may have no common safe color; report that instead of claiming AA.
  function readable(backgrounds, preferred, minimum = 4.5) {
    const target = colorValue(preferred);
    if (backgrounds.every(bg => getContrast(target, bg) >= minimum)) return target;
    const candidates = new Set([target, '#000000', '#ffffff']);
    for (let i = 0; i <= 50; i++) {
      candidates.add(mix(target, '#000000', i / 50));
      candidates.add(mix(target, '#ffffff', i / 50));
    }
    for (let n = 0; n <= 255; n++) candidates.add(hex([n,n,n]));
    const targetRgb = rgb(target);
    let best = '#000000', bestRatio = -1, safe = null, distance = Infinity;
    for (const candidate of candidates) {
      const ratio = Math.min(...backgrounds.map(bg => getContrast(candidate, bg)));
      if (ratio > bestRatio) { best = candidate; bestRatio = ratio; }
      if (ratio >= minimum) {
        const d = rgb(candidate).reduce((sum, n, i) => sum + (n - targetRgb[i]) ** 2, 0);
        if (d < distance) { safe = candidate; distance = d; }
      }
    }
    return safe || best;
  }
  function createDefaultTheme() {
    return {version:1, mode:'system',
      light:{colors:{primary:'#16766a', background:'#edf3ef', surface:'#fbfdf9', accent:'#efcf63'}, overrides:{}},
      dark:{colors:{primary:'#70c3a6', background:'#122222', surface:'#1a302e', accent:'#edcb69'}, overrides:{}}};
  }
  // Validate descriptors before reading values; reject unknown keys, getters,
  // symbols and custom prototypes. Ordinary records from other realms are OK.
  function record(value, allowed, required, label) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError(label + ' 必须是对象');
    const proto = Object.getPrototypeOf(value);
    if (proto !== null && proto !== Object.prototype) {
      const constructor = Object.getOwnPropertyDescriptor(proto, 'constructor');
      if (Object.getPrototypeOf(proto) !== null || !constructor || !('value' in constructor) ||
          typeof constructor.value !== 'function' || constructor.value.prototype !== proto ||
          Function.prototype.toString.call(constructor.value) !== 'function Object() { [native code] }') {
        throw new TypeError(label + ' 不接受自定义原型');
      }
    }
    const descriptors = Object.getOwnPropertyDescriptors(value), output = Object.create(null);
    for (const key of Reflect.ownKeys(descriptors)) {
      if (typeof key !== 'string' || !allowed.includes(key)) throw new TypeError(label + ' 含未知字段');
      const descriptor = descriptors[key];
      if (!('value' in descriptor) || !descriptor.enumerable) throw new TypeError(label + ' 不接受访问器或隐藏字段');
      output[key] = descriptor.value;
    }
    for (const key of required) if (!Object.prototype.hasOwnProperty.call(output, key)) throw new TypeError(label + ' 缺少 ' + key);
    return output;
  }
  function validateProfile(value, label) {
    const profile = record(value, ['colors','overrides'], ['colors','overrides'], label);
    const colors = record(profile.colors, BASE_KEYS, BASE_KEYS, label + '.colors');
    const overrides = record(profile.overrides, OVERRIDE_KEYS, [], label + '.overrides');
    const result = {colors:{}, overrides:{}};
    BASE_KEYS.forEach(key => { result.colors[key] = colorValue(colors[key]); });
    Object.keys(overrides).forEach(key => { result.overrides[key] = colorValue(overrides[key]); });
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
    if (typeof text !== 'string' || utf8Length(text) > MAX_JSON_BYTES) throw new TypeError('主题 JSON 不得超过 32768 字节');
    return validateTheme(JSON.parse(text));
  }
  function validateTheme(value) {
    if (typeof value === 'string') return parseThemeJSON(value);
    const theme = record(value, ['version','mode','light','dark'], ['version','mode','light','dark'], '主题');
    if (theme.version !== 1 || !MODES.includes(theme.mode)) throw new TypeError('不支持的主题版本或模式');
    return {version:1, mode:theme.mode, light:validateProfile(theme.light, 'light'), dark:validateProfile(theme.dark, 'dark')};
  }
  function deriveTokens(value, dark) {
    const profile = validateProfile(value, 'profile'), cacheKey = JSON.stringify([profile, !!dark]);
    if (tokenCache.has(cacheKey)) return tokenCache.get(cacheKey);
    const c = profile.colors, o = profile.overrides, backgrounds = [c.background, c.surface];
    const text = o.text || readable(backgrounds, dark ? '#edf5eb' : '#163432');
    const muted = o.muted || readable(backgrounds, mix(text, c.surface, .3));
    const subtle = mix(c.surface, c.primary, .1);
    const hero = o.hero || mix(c.surface, c.primary, dark ? .1 : .15);
    const art = mix(c.primary, '#101820', .75), artBack = c.accent;
    const tokens = {
      '--bg':c.background, '--panel':c.surface, '--panel-raised':c.surface,
      '--text':text, '--muted':muted, '--line':o.border || mix(c.surface, text, .22),
      '--brand':c.primary, '--brand-strong':c.primary, '--brand2':c.accent, '--accent':c.accent,
      '--accent-blue':readable(backgrounds, '#6679df'), '--accent-coral':readable(backgrounds, '#df7759'),
      '--on-brand':readable([c.primary], '#ffffff'), '--on-accent':readable([c.accent], '#163432'),
      '--subtle-bg':subtle, '--selected-fg':o.selected || readable([subtle], c.primary),
      '--hover-bg':mix(c.surface, c.primary, .06), '--link':o.link || readable(backgrounds, c.primary),
      '--focus-ring':readable(backgrounds, c.primary, 3),
      '--wash-a':c.accent + '18', '--wash-b':c.primary + '0c', '--page-backdrop':c.background,
      '--hero-bg':hero, '--hero-gradient':'linear-gradient(120deg,' + hero + ',' + hero + ')',
      '--hero-text':readable([hero], text), '--hero-muted':readable([hero], muted),
      '--art-shade':art, '--art-background':art, '--art-hue':'0deg', '--art-saturation':'1',
      '--art-label':readable([art], '#eaf3de'), '--art-route':readable([art], c.accent),
      '--art-node':c.accent, '--art-node-text':readable([c.accent, artBack], '#163432'),
      '--art-node-back':artBack, '--art-edge':readable([art], mix(c.accent, '#ffffff', .35), 3),
      '--code-bg':mix(c.surface, c.background, .5),
      '--shadow':dark ? '0 18px 42px rgba(0,0,0,.24)' : '0 16px 38px rgba(0,0,0,.1)'
    };
    tokens['--code-text'] = readable([tokens['--code-bg']], text);
    for (const [name, color] of [['success','#17834b'], ['warning','#a66b00'], ['danger','#c73545'], ['info','#3478c9']]) {
      const background = mix(c.surface, color, .12);
      tokens['--' + name + '-bg'] = background;
      tokens['--' + name] = readable([background, c.surface, c.background], color);
    }
    if (tokenCache.size > 80) tokenCache.clear();
    const result = Object.freeze(tokens); tokenCache.set(cacheKey, result); return result;
  }
  function contrastChecks(profile, dark) {
    const t = deriveTokens(profile, dark), checks = [];
    const add = (label, foreground, background, minimum = 4.5) => {
      const ratio = getContrast(t[foreground], t[background]);
      checks.push({label, foreground, background, ratio, minimum, pass:ratio >= minimum});
    };
    for (const [name, token] of [['正文','--text'], ['次要文字','--muted'], ['链接','--link']]) {
      add(name + ' / 页面', token, '--bg'); add(name + ' / 卡片', token, '--panel');
    }
    add('选中项', '--selected-fg', '--subtle-bg');
    add('主色按钮', '--on-brand', '--brand-strong'); add('强调色按钮', '--on-accent', '--accent');
    add('横幅正文', '--hero-text', '--hero-bg'); add('横幅说明', '--hero-muted', '--hero-bg');
    add('图谱标签', '--art-label', '--art-shade'); add('图谱节点', '--art-node-text', '--art-node');
    add('图谱背面节点', '--art-node-text', '--art-node-back'); add('代码', '--code-text', '--code-bg');
    return checks;
  }
  function repairProfile(value, dark) {
    const profile = validateProfile(value, 'profile');
    const backgrounds = [profile.colors.background, profile.colors.surface];
    const candidate = readable(backgrounds, dark ? '#ffffff' : '#000000');
    if (backgrounds.some(bg => getContrast(candidate, bg) < 4.5)) profile.colors.surface = profile.colors.background;
    for (const key of ['text','muted','link','selected']) delete profile.overrides[key];
    if (contrastChecks(profile, dark).some(check => !check.pass)) throw new Error('无法修复已检查的颜色对，请调整基础色');
    return profile;
  }

  let current = null, draft = null, snapshot = null, editMode = 'light';
  let library = [], media = null, waiting = false, startupWarning = '', returnFocus = null;
  const invalidFields = new Set(), ui = {};
  function storageRead(key) {
    try { return window.localStorage.getItem(key); }
    catch (_) { startupWarning = '浏览器存储不可用：仍可预览或仅在本页应用主题。'; return null; }
  }
  function storageWrite(key, value) {
    try { window.localStorage.setItem(key, value); return true; } catch (_) { return false; }
  }
  function validateLibrary(value) {
    const payload = record(value, ['version','schemes'], ['version','schemes'], '命名方案库');
    if (payload.version !== 1 || !Array.isArray(payload.schemes) || payload.schemes.length > 12) throw new TypeError('命名方案库无效');
    const names = new Set();
    return payload.schemes.map(value => {
      const entry = record(value, ['name','theme'], ['name','theme'], '命名方案');
      if (typeof entry.name !== 'string' || !entry.name.trim() || entry.name.length > 40 || names.has(entry.name)) throw new TypeError('方案名称无效');
      names.add(entry.name); return {name:entry.name, theme:validateTheme(entry.theme)};
    });
  }
  function ensureState() {
    if (current) return;
    current = createDefaultTheme();
    const stored = storageRead(THEME_KEY);
    if (stored !== null) {
      try { current = parseThemeJSON(stored); }
      catch (_) { startupWarning = '已存主题无效，当前使用默认颜色；保存后可替换无效数据。'; }
    } else {
      const oldMode = storageRead('theme');
      if (oldMode === 'light' || oldMode === 'dark') current.mode = oldMode;
    }
    const storedLibrary = storageRead(LIBRARY_KEY);
    if (storedLibrary !== null) {
      try {
        if (utf8Length(storedLibrary) > MAX_JSON_BYTES) throw new TypeError('方案库过大');
        library = validateLibrary(JSON.parse(storedLibrary));
      } catch (_) { library = []; startupWarning = '命名方案库无效，已忽略；主题仍可正常编辑。'; }
    }
    try { media = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)') : null; } catch (_) { media = null; }
    if (media) {
      const changed = () => {
        if (draft) apply(draft, editMode);
        else if (current.mode === 'system') apply(current);
      };
      if (typeof media.addEventListener === 'function') media.addEventListener('change', changed);
      else if (typeof media.addListener === 'function') media.addListener(changed);
    }
  }
  function resolveMode(mode) { return mode === 'system' ? (media && media.matches ? 'dark' : 'light') : mode; }
  function setTokens(element, tokens) {
    if (element && element.style) Object.entries(tokens).forEach(([key, value]) => element.style.setProperty(key, value));
  }
  function apply(theme, forcedMode) {
    if (!document || !document.documentElement || !document.body) return;
    const resolved = forcedMode || resolveMode(theme.mode);
    const tokens = deriveTokens(theme[resolved], resolved === 'dark');
    const root = document.documentElement, body = document.body;
    root.dataset.palette = 'custom'; root.dataset.customTheme = 'true'; root.dataset.theme = resolved;
    body.dataset.theme = resolved; body.dataset.customTheme = 'true';
    root.style.colorScheme = resolved; body.style.colorScheme = resolved;
    setTokens(root, tokens); setTokens(body, tokens);
    if (draft && ui.preview) setTokens(ui.preview, tokens);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', tokens['--bg']);
  }
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function button(text, action, className = '') {
    const node = element('button', 'btn ' + className, text);
    node.type = 'button'; node.addEventListener('click', action); return node;
  }
  function labeledSelect(id, title, choices) {
    const label = element('label', 'theme-select-label', title); label.htmlFor = id;
    const select = element('select'); select.id = id;
    choices.forEach(([value, title]) => { const option = element('option', '', title); option.value = value; select.append(option); });
    const wrapper = element('div', 'theme-select-row'); wrapper.append(label, select); return {wrapper, select};
  }
  function ensureStylesheet() {
    if (!document.head) return;
    let link = document.getElementById('acm-theme-editor-styles');
    if (!link) { link = element('link'); link.id = 'acm-theme-editor-styles'; link.rel = 'stylesheet'; link.href = '/assets/theme-editor.css?v=custom-theme-1'; }
    document.head.append(link);
  }
  function notify(message, error = false) {
    for (const node of [ui.status, ui.outerStatus]) if (node) {
      node.textContent = message; node.dataset.kind = error ? 'error' : 'info'; node.dataset.state = error ? 'error' : 'info';
    }
  }
  function mountControls() {
    if (ui.controls && ui.controls.isConnected !== false) return;
    const host = document.querySelector('#theme-toggle')?.parentElement || document.querySelector('.forum-header-actions') ||
      document.querySelector('.topbar .userbar') || document.querySelector('.topbar') || document.querySelector('.login > .card') ||
      document.querySelector('#change-password-panel form') || document.querySelector('.login form');
    if (!host) return;
    ui.controls = element('div', 'theme-controls'); ui.trigger = button('自助调色', open, 'theme-trigger');
    ui.trigger.setAttribute('aria-haspopup', 'dialog'); ui.trigger.setAttribute('aria-controls', 'theme-editor');
    ui.trigger.setAttribute('aria-expanded', 'false'); ui.trigger.title = '自定义浅色、深色主题';
    ui.outerStatus = element('span', 'theme-status theme-controls-status'); ui.outerStatus.setAttribute('role', 'status'); ui.outerStatus.setAttribute('aria-live', 'polite');
    ui.controls.append(ui.trigger, ui.outerStatus); host.append(ui.controls);
  }
  function init() {
    ensureState();
    if (!document) return false;
    ensureStylesheet();
    if (!document.body) {
      if (!waiting && typeof document.addEventListener === 'function') {
        waiting = true; document.addEventListener('DOMContentLoaded', () => { waiting = false; init(); }, {once:true});
      }
      return false;
    }
    mountControls(); apply(draft || current, draft ? editMode : undefined);
    if (startupWarning) { notify(startupWarning, true); startupWarning = ''; }
    return true;
  }
  function toggle() {
    init();
    if (draft) {
      editMode = editMode === 'dark' ? 'light' : 'dark'; draft.mode = editMode;
      renderDraft(); notify('已切换草稿主题；取消可恢复，保存后才会持久化。'); return editMode;
    }
    const next = clone(current); next.mode = resolveMode(current.mode) === 'dark' ? 'light' : 'dark';
    current = next; apply(current);
    const saved = storageWrite(THEME_KEY, JSON.stringify(current));
    notify(saved ? '已切换并保存主题模式。' : '当前页已切换，但浏览器存储失败，未保存。', !saved); return current.mode;
  }
  function ensureDialog() {
    if (ui.dialog) return;
    const dialog = element('dialog', 'theme-editor'); dialog.id = 'theme-editor'; dialog.setAttribute('aria-labelledby', 'theme-editor-title'); ui.dialog = dialog;
    const header = element('div', 'theme-editor-header');
    const title = element('h2', '', '自助调色'); title.id = 'theme-editor-title';
    const close = button('×', cancelChanges, 'theme-close'); close.setAttribute('aria-label', '取消并关闭调色面板'); header.append(title, close);
    const body = element('div', 'theme-editor-body');
    const help = element('p', 'theme-help', '修改实时预览，保存才写入浏览器。关闭、Esc 或取消会恢复打开面板时的主题。');
    const selectors = element('div', 'theme-mode-controls');
    const mode = labeledSelect('theme-mode', '保存后的主题模式', [['light','浅色'], ['dark','深色'], ['system','跟随系统']]);
    const edit = labeledSelect('theme-edit-mode', '正在编辑并预览', [['light','浅色颜色'], ['dark','深色颜色']]);
    ui.mode = mode.select; ui.editMode = edit.select; selectors.append(mode.wrapper, edit.wrapper);
    const base = element('section', 'theme-section theme-basic'); base.append(element('h3', '', '基础颜色'));
    ui.baseFields = element('div', 'theme-color-fields'); base.append(ui.baseFields);
    const advanced = element('details', 'theme-section theme-advanced'); advanced.append(element('summary', '', '高级调色 · 文字与细节'));
    advanced.append(element('p', 'theme-help', '默认自动适配。输入 HEX 或选色会启用手动覆盖，留空或点“自动”可恢复。'));
    ui.advancedFields = element('div', 'theme-color-fields'); advanced.append(ui.advancedFields);
    ui.preview = element('div', 'theme-preview');
    ui.preview.append(element('strong', '', '主题预览'), element('p', 'theme-preview-text', '正文与页面、卡片颜色'), element('p', 'theme-preview-muted', '次要信息与说明'));
    const previewLink = element('a', 'theme-preview-link', '示例链接'); previewLink.href = '#'; previewLink.addEventListener('click', event => event.preventDefault());
    const previewButtons = element('div', 'theme-actions'); previewButtons.append(button('主色按钮', () => {}, 'primary theme-preview-primary'), button('强调色按钮', () => {}, 'theme-preview-accent'));
    const previewHero = element('div', 'theme-preview-hero'); previewHero.append(element('strong', '', '欢迎横幅'), element('p', '', '横幅次要文字'));
    ui.preview.append(previewLink, previewButtons, previewHero);
    const checks = element('section', 'theme-section theme-contrast-section'); checks.append(element('h3', '', '可读性检查 · 4.5:1'));
    ui.checks = element('ul', 'theme-contrast'); checks.append(ui.checks);
    checks.append(element('p', 'theme-help', '手动低对比颜色仍可保存。修复仅影响当前编辑模式；若页面和卡片无法共享安全文字色，会协调卡片背景。检查不代表全页面无障碍认证。'));
    checks.append(button('一键修复已检查色对', repairDraft, 'theme-repair'));
    const librarySection = element('section', 'theme-section theme-library'); librarySection.append(element('h3', '', '我的配色 · 最多 12 个'));
    const nameLabel = element('label', '', '方案名称'); nameLabel.htmlFor = 'theme-scheme-name';
    ui.name = element('input'); ui.name.id = 'theme-scheme-name'; ui.name.type = 'text'; ui.name.maxLength = 40; ui.name.placeholder = '给这套配色起个名字';
    const schemeActions = element('div', 'theme-actions'); schemeActions.append(ui.name, button('另存命名方案', saveScheme, 'theme-scheme-save'));
    librarySection.append(nameLabel, schemeActions, element('p', 'theme-help', '另存只写入方案库；加载只进入草稿，不会保存当前主题。'));
    ui.library = element('div', 'theme-library-list'); librarySection.append(ui.library);
    const transfer = element('section', 'theme-section theme-transfer'); transfer.append(element('h3', '', '导入 / 导出'));
    ui.file = element('input'); ui.file.type = 'file'; ui.file.accept = '.json,application/json'; ui.file.id = 'theme-import-file'; ui.file.hidden = true; ui.file.addEventListener('change', importFile);
    const transferActions = element('div', 'theme-actions'); transferActions.append(button('导入 JSON 至草稿', () => ui.file.click(), 'theme-import'), button('导出当前草稿', exportDraft, 'theme-export'), ui.file);
    transfer.append(transferActions, element('p', 'theme-help', '最多 32 KB，仅导入颜色数据，不接受 CSS、脚本或资源地址。导入后仍需保存。'));
    ui.status = element('p', 'theme-status'); ui.status.setAttribute('role', 'status'); ui.status.setAttribute('aria-live', 'polite');
    body.append(help, selectors, base, advanced, ui.preview, checks, librarySection, transfer, ui.status);
    const footer = element('div', 'theme-editor-footer');
    footer.append(button('恢复当前模式默认颜色', resetDraft, 'theme-reset'), button('取消', cancelChanges, 'theme-cancel'), button('仅本页应用', applyForPage, 'theme-apply-page'), button('保存主题', saveDraft, 'primary theme-save'));
    dialog.append(header, body, footer); document.body.append(dialog);
    ui.mode.addEventListener('change', () => { if (!draft) return; draft.mode = ui.mode.value; apply(draft, editMode); notify('保存模式已修改；当前仍预览正在编辑的 ' + (editMode === 'dark' ? '深色' : '浅色') + '。'); });
    ui.editMode.addEventListener('change', () => { if (!draft) return; editMode = ui.editMode.value; renderDraft(); notify('已切换编辑颜色；保存模式未改变。'); });
    dialog.addEventListener('cancel', event => { event.preventDefault(); cancelChanges(); });
    dialog.addEventListener('close', () => { if (draft) cancelChanges(); });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) cancelChanges();
    });
  }
  function syncAutomaticFields() {
    if (!draft || !ui.advancedFields) return;
    const profile = draft[editMode], tokens = deriveTokens(profile, editMode === 'dark');
    for (const key of OVERRIDE_KEYS) {
      if (Object.prototype.hasOwnProperty.call(profile.overrides, key)) continue;
      const picker = document.getElementById('theme-color-' + key), input = document.getElementById('theme-hex-' + key);
      if (picker) picker.value = tokens[OVERRIDE_TOKENS[key]];
      if (input) input.placeholder = '自动 ' + tokens[OVERRIDE_TOKENS[key]];
    }
  }
  function renderFields() {
    invalidFields.clear(); ui.baseFields.replaceChildren(); ui.advancedFields.replaceChildren();
    const profile = draft[editMode], tokens = deriveTokens(profile, editMode === 'dark');
    for (const key of BASE_KEYS.concat(OVERRIDE_KEYS)) {
      const advanced = OVERRIDE_KEYS.includes(key), manual = advanced && Object.prototype.hasOwnProperty.call(profile.overrides, key);
      const effective = advanced ? (profile.overrides[key] || tokens[OVERRIDE_TOKENS[key]]) : profile.colors[key];
      const row = element('div', 'theme-color-row'); row.dataset.field = key; row.dataset.overridden = String(!!manual);
      const label = element('label', 'theme-color-label', LABELS[key]); label.id = 'theme-label-' + key;
      const picker = element('input', 'theme-color-picker'); picker.type = 'color'; picker.id = 'theme-color-' + key; picker.value = effective; picker.setAttribute('aria-labelledby', label.id);
      const input = element('input', 'theme-color-hex'); input.type = 'text'; input.id = 'theme-hex-' + key;
      input.value = advanced && !manual ? '' : effective; input.placeholder = advanced ? '自动 ' + effective : '#RRGGBB';
      input.maxLength = 7; input.autocomplete = 'off'; input.spellcheck = false; label.htmlFor = input.id;
      input.setAttribute('aria-label', LABELS[key] + ' HEX'); input.setAttribute('aria-invalid', 'false');
      const marker = element('span', 'theme-color-auto', advanced ? (manual ? '手动覆盖' : '自动推导') : '');
      const update = source => {
        if (!draft) return;
        const value = source === picker ? picker.value : input.value, normalized = normalizeColor(value);
        if (advanced && value.trim() === '') {
          delete draft[editMode].overrides[key]; invalidFields.delete(key); input.setAttribute('aria-invalid', 'false');
          const automatic = deriveTokens(draft[editMode], editMode === 'dark')[OVERRIDE_TOKENS[key]];
          picker.value = automatic; input.placeholder = '自动 ' + automatic; marker.textContent = '自动推导'; row.dataset.overridden = 'false';
        } else if (!normalized) {
          invalidFields.add(key); input.setAttribute('aria-invalid', 'true'); notify(LABELS[key] + '：请输入 #RGB 或 #RRGGBB；非法值不会应用。', true); return;
        } else {
          invalidFields.delete(key); input.setAttribute('aria-invalid', 'false');
          (advanced ? draft[editMode].overrides : draft[editMode].colors)[key] = normalized; picker.value = normalized;
          if (source === picker) input.value = normalized;
          if (advanced) { marker.textContent = '手动覆盖'; row.dataset.overridden = 'true'; }
        }
        apply(draft, editMode); syncAutomaticFields(); renderChecks();
      };
      picker.addEventListener('input', () => update(picker)); input.addEventListener('input', () => update(input));
      input.addEventListener('blur', () => { const normalized = normalizeColor(input.value); if (normalized) input.value = normalized; });
      row.append(label, picker, input);
      if (advanced) {
        row.append(button('自动', () => { if (!draft) return; delete draft[editMode].overrides[key]; renderDraft(); notify('已恢复 ' + LABELS[key] + ' 的自动推导。'); }, 'theme-color-reset'), marker);
      }
      (advanced ? ui.advancedFields : ui.baseFields).append(row);
    }
  }
  function renderChecks() {
    if (!draft) return;
    ui.checks.replaceChildren(); const checks = contrastChecks(draft[editMode], editMode === 'dark');
    for (const check of checks) {
      const item = element('li', 'theme-contrast-item', (check.pass ? '通过 ' : '低对比 ') + check.label + '：' + check.ratio.toFixed(2) + ':1');
      item.dataset.pass = String(check.pass); ui.checks.append(item);
    }
    ui.checks.setAttribute('aria-label', checks.every(check => check.pass) ? '所有已检查色对通过' : '存在低对比色对；可手动保存或一键修复');
  }
  function renderLibrary() {
    ui.library.replaceChildren();
    if (!library.length) { ui.library.append(element('p', 'theme-help', '暂无命名方案。')); return; }
    library.forEach((entry, index) => {
      const row = element('div', 'theme-library-row'), name = element('span', 'theme-library-name', entry.name);
      const load = button('加载至草稿', () => { if (!draft) return; draft = clone(entry.theme); editMode = resolveMode(draft.mode); ui.name.value = entry.name; renderDraft(); notify('已加载命名方案至草稿，尚未保存当前主题。'); }, 'theme-library-load');
      load.setAttribute('aria-label', '加载方案 ' + entry.name);
      const remove = button('删除', () => {
        const next = library.filter((_, position) => position !== index);
        if (!storageWrite(LIBRARY_KEY, JSON.stringify({version:1, schemes:next}))) { notify('存储失败，命名方案未删除。', true); return; }
        library = next; renderLibrary(); notify('命名方案已删除；当前主题和草稿未改变。');
      }, 'theme-library-delete');
      remove.setAttribute('aria-label', '删除方案 ' + entry.name); row.append(name, load, remove); ui.library.append(row);
    });
  }
  function renderDraft() {
    if (!draft) return;
    ui.mode.value = draft.mode; ui.editMode.value = editMode;
    apply(draft, editMode); renderFields(); renderChecks(); renderLibrary();
  }
  function validInputs() {
    if (!invalidFields.size) return true;
    notify('存在无效 HEX 输入，请修正后继续。', true);
    const first = document.getElementById('theme-hex-' + invalidFields.values().next().value); if (first) first.focus(); return false;
  }
  function open() {
    if (!init()) return false;
    ensureDialog();
    if (draft) { ui.mode.focus(); return true; }
    if (typeof ui.dialog.showModal !== 'function') { notify('浏览器不支持原生 dialog，请升级浏览器。', true); return false; }
    returnFocus = document.activeElement; snapshot = clone(current); draft = clone(current); editMode = resolveMode(draft.mode);
    ui.name.value = ''; renderDraft(); notify('预览未保存。正在编辑' + (editMode === 'dark' ? '深色' : '浅色') + '；保存模式：' + ({light:'浅色',dark:'深色',system:'跟随系统'}[draft.mode]) + '。');
    try { ui.dialog.showModal(); }
    catch (_) { current = snapshot; draft = null; snapshot = null; apply(current); notify('无法打开调色面板。', true); return false; }
    if (ui.trigger) ui.trigger.setAttribute('aria-expanded', 'true'); ui.mode.focus(); return true;
  }
  function closePanel() {
    invalidFields.clear(); if (ui.trigger) ui.trigger.setAttribute('aria-expanded', 'false');
    if (ui.dialog && ui.dialog.open) ui.dialog.close();
    const focus = returnFocus && returnFocus.isConnected !== false ? returnFocus : ui.trigger;
    if (focus && typeof focus.focus === 'function') focus.focus(); returnFocus = null;
  }
  function cancelChanges() {
    if (!draft) return;
    current = snapshot; draft = null; snapshot = null; apply(current); closePanel(); notify('已取消，恢复打开面板时的主题。');
  }
  function saveDraft() {
    if (!draft || !validInputs()) return;
    const next = validateTheme(draft);
    if (!storageWrite(THEME_KEY, JSON.stringify(next))) { notify('浏览器存储失败，未保存。可选“仅本页应用”；取消会恢复原主题。', true); return; }
    current = next; draft = null; snapshot = null; apply(current); closePanel(); notify('主题已保存。');
  }
  function applyForPage() {
    if (!draft || !validInputs()) return;
    current = validateTheme(draft); draft = null; snapshot = null; apply(current); closePanel(); notify('已仅在本页应用主题，未写入存储；刷新后使用此前保存的主题。');
  }
  function repairDraft() {
    if (!draft) return;
    const oldSurface = draft[editMode].colors.surface;
    try {
      draft[editMode] = repairProfile(draft[editMode], editMode === 'dark'); renderDraft();
      notify(oldSurface !== draft[editMode].colors.surface ? '已修复已检查色对，并协调卡片背景以获得共同安全文字色；尚未保存。' : '已修复已检查色对；尚未保存。');
    } catch (error) { notify(error.message, true); }
  }
  function resetDraft() {
    if (!draft) return;
    draft[editMode] = createDefaultTheme()[editMode]; renderDraft(); notify('当前编辑模式已恢复默认颜色，尚未保存。');
  }
  function saveScheme() {
    if (!draft || !validInputs()) return;
    const name = ui.name.value.trim();
    if (!name || name.length > 40) { notify('方案名称不能为空且最多 40 个字符。', true); ui.name.focus(); return; }
    const next = library.map(entry => ({name:entry.name, theme:clone(entry.theme)})), existing = next.findIndex(entry => entry.name === name);
    if (existing === -1 && next.length >= 12) { notify('最多保存 12 个命名方案，请先删除一个。', true); return; }
    const entry = {name, theme:validateTheme(draft)}; if (existing === -1) next.push(entry); else next[existing] = entry;
    if (!storageWrite(LIBRARY_KEY, JSON.stringify({version:1, schemes:next}))) { notify('存储失败，命名方案未保存；当前草稿不变。', true); return; }
    library = next; renderLibrary(); notify('命名方案已保存；当前主题仍是未保存草稿。');
  }
  function readFile(file) {
    if (typeof file.text === 'function') return file.text();
    return new Promise((resolve, reject) => {
      if (typeof window.FileReader !== 'function') { reject(new Error('浏览器不支持文件读取')); return; }
      const reader = new window.FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('无法读取主题文件'));
      reader.onabort = () => reject(new Error('文件读取已取消')); reader.readAsText(file);
    });
  }
  async function importFile() {
    const file = ui.file.files && ui.file.files[0], session = draft; if (!file || !session) return;
    try {
      if (file.size > MAX_JSON_BYTES) throw new Error('主题文件不得超过 32768 字节');
      const contents = await readFile(file); if (draft !== session) return;
      draft = parseThemeJSON(contents); editMode = resolveMode(draft.mode); renderDraft(); notify('JSON 已导入至草稿，尚未保存。');
    } catch (error) { if (draft === session) notify('导入失败：' + error.message, true); }
    finally { ui.file.value = ''; }
  }
  function exportDraft() {
    if (!draft || !validInputs()) return;
    let url = null;
    try {
      const data = JSON.stringify(validateTheme(draft), null, 2); if (utf8Length(data) > MAX_JSON_BYTES) throw new Error('主题 JSON 过大');
      const blob = new window.Blob([data], {type:'application/json'}); url = window.URL.createObjectURL(blob);
      const anchor = element('a'); anchor.href = url; anchor.download = 'acm-forever-theme.json'; document.body.append(anchor); anchor.click(); anchor.remove();
      notify('已导出主题 JSON；不包含命名方案库，也未保存草稿。');
    } catch (error) { notify('导出失败：' + error.message, true); }
    finally { if (url) { const revoke = () => window.URL.revokeObjectURL(url); if (typeof window.setTimeout === 'function') window.setTimeout(revoke, 1000); else revoke(); } }
  }
  window.ACMTheme = Object.freeze({init, toggle, open, deriveTokens, getContrast, normalizeColor, validateTheme, createDefaultTheme, parseThemeJSON, contrastChecks, repairProfile});
})(window);
