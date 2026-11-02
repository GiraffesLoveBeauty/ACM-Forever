<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { markdown, controlledImage } from '../lib/markdown.js';
import { headingSlug } from '../lib/wiki.js';
const props = defineProps({ source: { type: String, default: '' } });
const emit = defineEmits(['toc', 'active']);
const root = ref(),
  message = ref(''),
  viewer = ref(),
  viewed = ref('');
let observer,
  groups = [];
async function enhance() {
  await nextTick();
  if (!root.value) return;
  observer?.disconnect();
  groups = [];
  const counts = new Map(),
    toc = [];
  root.value.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((node, index) => {
    const base = headingSlug(node.textContent, `section-${index + 1}`),
      count = counts.get(base) || 0;
    counts.set(base, count + 1);
    node.id = count ? `${base}-${count + 1}` : base;
    toc.push({ id: node.id, title: node.textContent, level: Number(node.tagName[1]) });
  });
  emit('toc', toc);
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) emit('active', visible[0].target.id);
      },
      { rootMargin: '-100px 0px -60% 0px' },
    );
    root.value.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((node) => observer.observe(node));
  }
  for (const pre of root.value.querySelectorAll('pre')) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn code-copy';
    button.dataset.copy = '';
    button.textContent = '复制代码';
    pre.append(button);
  }
  const pres = [...root.value.querySelectorAll('pre')];
  for (let index = 0; index < pres.length; index++) {
    const set = [pres[index]];
    let next = pres[index].nextElementSibling;
    while (next?.tagName === 'PRE') {
      set.push(next);
      index++;
      next = next.nextElementSibling;
    }
    const names = set.map(
      (pre) => /language-([\w+-]+)/.exec(pre.querySelector('code')?.className || '')?.[1],
    );
    if (set.length > 1 && names.every(Boolean) && new Set(names).size === names.length) {
      const tabs = document.createElement('div');
      tabs.className = 'chips code-languages';
      tabs.setAttribute('role', 'group');
      tabs.setAttribute('aria-label', '代码语言');
      const group = groups.push(set) - 1;
      set[0].before(tabs);
      names.forEach((name, i) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = name;
        b.className = 'btn';
        b.dataset.group = group;
        b.dataset.index = i;
        b.setAttribute('aria-pressed', String(i === 0));
        tabs.append(b);
        set[i].hidden = i !== 0;
      });
    }
  }
  root.value.querySelectorAll('img').forEach((image) => {
    image.tabIndex = 0;
    image.setAttribute('role', 'button');
    image.setAttribute('aria-label', `查看图片：${image.alt || '正文图片'}`);
  });
  if (location.hash) {
    try {
      root.value.querySelectorAll('[id]').forEach((node) => {
        if (node.id === decodeURIComponent(location.hash.slice(1))) node.scrollIntoView();
      });
    } catch {
      /* Invalid hashes do not block reading. */
    }
  }
}
async function action(event) {
  const target = event.target;
  const copy = target.closest?.('[data-copy]');
  if (copy) {
    try {
      await navigator.clipboard.writeText(copy.closest('pre').querySelector('code').textContent);
      message.value = '代码已复制。';
    } catch {
      message.value = '复制失败，请选择代码后手动复制。';
    }
    return;
  }
  if (target.dataset?.group != null) {
    const set = groups[Number(target.dataset.group)];
    set?.forEach((node, index) => (node.hidden = index !== Number(target.dataset.index)));
    for (const b of target.parentElement.children)
      b.setAttribute('aria-pressed', String(b === target));
    return;
  }
  if (target.tagName === 'IMG' && controlledImage(target.getAttribute('src'))) {
    viewed.value = target.src;
    viewer.value.showModal();
  }
}
function keydown(event) {
  if (event.target.tagName === 'IMG' && ['Enter', ' '].includes(event.key)) {
    event.preventDefault();
    action(event);
  }
}
function imageError(event) {
  const target = event.target;
  if (target.tagName === 'IMG') {
    const note = document.createElement('span');
    note.textContent = `图片暂不可用：${target.alt || '正文图片'}，请稍后刷新重试。`;
    target.replaceWith(note);
  }
}
watch(() => props.source, enhance, { immediate: true, flush: 'post' });
onBeforeUnmount(() => observer?.disconnect());
</script>
<template>
  <article
    ref="root"
    v-forum-math
    class="forum-markdown wiki-body"
    @click="action"
    @keydown="keydown"
    @error.capture="imageError"
    v-html="markdown(source)"
  ></article>
  <p v-if="message" role="status">{{ message }}</p>
  <dialog ref="viewer" class="wiki-image-viewer" @click.self="viewer.close()">
    <button class="btn" @click="viewer.close()">关闭图片</button
    ><img :src="viewed" alt="正文图片放大查看" />
  </dialog>
</template>
