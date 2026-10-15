import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { compileScript, parse } from 'vue/compiler-sfc';
import { createRenderer, nextTick } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

const web = fileURLToPath(new URL('../../', import.meta.url));
const compiled = await mkdtemp(resolve(web, 'node_modules/.vue-regression-'));
const modules = new Map();
const stub = resolve(compiled, 'stub.mjs');
await writeFile(stub, 'export default { render() { return null; } };\n');

export async function loadSfc(file) {
  const path = resolve(web, file);
  if (modules.has(path)) return modules.get(path);
  const target = resolve(compiled, `${modules.size}.mjs`);
  modules.set(path, pathToFileURL(target).href);
  const { descriptor } = parse(await readFile(path, 'utf8'), { filename: path });
  let source = compileScript(descriptor, { id: file, inlineTemplate: true }).content;
  const imports = [...source.matchAll(/from (['"])(\.[^'"]+)\1/g)];
  for (const match of imports) {
    const imported = resolve(dirname(path), match[2]);
    const url = /(?:ThemeEditor|GraphArt)\.vue$/.test(imported)
      ? pathToFileURL(stub).href
      : imported.endsWith('.vue')
        ? await loadSfc(relative(web, imported))
        : pathToFileURL(imported).href;
    source = source.replace(match[0], `from '${url}'`);
  }
  await writeFile(target, source);
  return pathToFileURL(target).href;
}

function node(type, text = '') {
  return {
    type,
    tagName: type.toUpperCase(),
    text,
    props: {},
    children: [],
    parent: null,
    listeners: new Map(),
    getRootNode() {
      return globalThis.document;
    },
    get options() {
      const collect = (target) =>
        target.type === 'option' ? [target] : target.children.flatMap(collect);
      return this.children.flatMap(collect);
    },
    get multiple() {
      return Boolean(this.props.multiple);
    },
    addEventListener(name, handler) {
      this.listeners.set(name, handler);
    },
    removeEventListener(name) {
      this.listeners.delete(name);
    },
  };
}
function remove(child) {
  if (!child.parent) return;
  const children = child.parent.children;
  children.splice(children.indexOf(child), 1);
  child.parent = null;
}
function insert(child, parent, anchor = null) {
  remove(child);
  const index = anchor ? parent.children.indexOf(anchor) : -1;
  parent.children.splice(index < 0 ? parent.children.length : index, 0, child);
  child.parent = parent;
}
const renderer = createRenderer({
  createElement: (tag) => node(tag),
  createText: (text) => node('#text', text),
  createComment: (text) => node('#comment', text),
  setText: (target, text) => (target.text = text),
  setElementText(target, text) {
    for (const child of target.children) child.parent = null;
    target.children = [];
    target.text = text;
  },
  patchProp(target, key, previous, value) {
    target.props[key] = value;
    if (['value', 'checked', 'selected'].includes(key)) target[key] = value;
  },
  insert,
  remove,
  parentNode: (target) => target.parent,
  nextSibling: (target) =>
    target.parent?.children[target.parent.children.indexOf(target) + 1] || null,
  insertStaticContent(html, parent, anchor) {
    const target = node('#static', html);
    insert(target, parent, anchor);
    return [target, target];
  },
});

export function find(root, predicate) {
  const found = [];
  function visit(target) {
    if (predicate(target)) found.push(target);
    target.children.forEach(visit);
  }
  visit(root);
  return found;
}
export function textOf(target) {
  return target.text + target.children.map(textOf).join('');
}
export async function settle() {
  for (let i = 0; i < 6; i++) {
    await new Promise((done) => setImmediate(done));
    await nextTick();
  }
}
export async function mount(App, routes, path = '/index.html') {
  const root = node('root');
  const router = createRouter({ history: createMemoryHistory(), routes });
  const app = renderer.createApp(App);
  app.use(router);
  await router.push(path);
  await router.isReady();
  app.mount(root);
  await settle();
  return { root, router, unmount: () => app.unmount() };
}
export async function cleanupCompiled() {
  if (dirname(compiled) !== resolve(web, 'node_modules'))
    throw Error('Unexpected compiled test directory');
  await rm(compiled, { recursive: true, force: true });
}
