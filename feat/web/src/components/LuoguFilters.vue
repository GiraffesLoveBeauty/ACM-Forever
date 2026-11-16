<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRequests } from '../lib/api.js';
const props = defineProps({
  difficulty: { type: String, default: '' },
  tag: { type: String, default: '' },
  difficultyMin: { type: String, default: '' },
  difficultyMax: { type: String, default: '' },
  tags: { type: String, default: '' },
});
const emit = defineEmits([
  'update:difficulty',
  'update:tag',
  'update:difficultyMin',
  'update:difficultyMax',
  'update:tags',
]);
const request = useRequests(),
  taxonomy = ref({ difficulties: [], tags: [], tag_types: [] }),
  busy = ref(false),
  error = ref('');
const levels = computed(() => (taxonomy.value.difficulties || []).filter((item) => item.id !== 0));
const selectedTags = computed(() => [
  ...new Set([props.tag, ...props.tags.split(',')].filter(Boolean)),
]);
const lower = computed(() =>
  props.difficulty && props.difficulty !== '0' ? props.difficulty : props.difficultyMin,
);
const upper = computed(() =>
  props.difficulty && props.difficulty !== '0' ? props.difficulty : props.difficultyMax,
);
const groups = computed(() => {
  const groups = new Map();
  for (const tag of taxonomy.value.tags || []) {
    const name =
      (taxonomy.value.tag_types || []).find((type) => type.id === tag.type)?.name || '其他标签';
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(tag);
  }
  return [...groups].map(([name, items]) => ({ name, items }));
});
function range(key, value) {
  if (props.difficulty && props.difficulty !== '0') {
    emit('update:difficultyMin', props.difficulty);
    emit('update:difficultyMax', props.difficulty);
  }
  emit('update:difficulty', '');
  emit('update:' + key, value);
}
function unrated(value) {
  emit('update:difficulty', value ? '0' : '');
  emit('update:difficultyMin', '');
  emit('update:difficultyMax', '');
}
function tagChange(event) {
  emit('update:tag', '');
  emit('update:tags', [...event.target.selectedOptions].map((item) => item.value).join(','));
}
async function load() {
  busy.value = true;
  error.value = '';
  try {
    taxonomy.value = await request('/problems/taxonomy?platform=luogu', {}, 'luogu-taxonomy');
  } catch (cause) {
    if (cause.name !== 'AbortError') error.value = '洛谷分类暂时无法加载，仍可按题号查询。';
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="luogu-native-filters">
    <label
      ><span>洛谷难度下限</span
      ><select
        :value="lower"
        :disabled="busy || difficulty === '0'"
        @change="range('difficultyMin', $event.target.value)"
      >
        <option value="">不限下限</option>
        <option v-if="lower && !levels.some((item) => String(item.id) === lower)" :value="lower">
          难度 #{{ lower }}（名称待更新）
        </option>
        <option v-for="level in levels" :key="level.id" :value="String(level.id)">
          {{ level.name }}
        </option>
      </select></label
    >
    <label
      ><span>洛谷难度上限</span
      ><select
        :value="upper"
        :disabled="busy || difficulty === '0'"
        @change="range('difficultyMax', $event.target.value)"
      >
        <option value="">不限上限</option>
        <option v-if="upper && !levels.some((item) => String(item.id) === upper)" :value="upper">
          难度 #{{ upper }}（名称待更新）
        </option>
        <option v-for="level in levels" :key="level.id" :value="String(level.id)">
          {{ level.name }}
        </option>
      </select></label
    >
    <label class="luogu-unrated"
      ><input
        type="checkbox"
        :checked="difficulty === '0'"
        @change="unrated($event.target.checked)"
      /><span>只看暂无评定</span></label
    >
    <label class="luogu-tags"
      ><span>洛谷原生标签（可多选，同时满足）</span
      ><select multiple size="4" :disabled="busy" @change="tagChange">
        <option
          v-for="id in selectedTags.filter(
            (id) => !taxonomy.tags?.some((item) => String(item.id) === id),
          )"
          :key="id"
          :value="id"
          :selected="true"
        >
          标签 #{{ id }}（名称待更新）
        </option>
        <optgroup v-for="group in groups" :key="group.name" :label="group.name">
          <option
            v-for="tag in group.items"
            :key="tag.id"
            :value="String(tag.id)"
            :selected="selectedTags.includes(String(tag.id))"
          >
            {{ tag.name }}
          </option>
        </optgroup></select
      ><button
        v-if="selectedTags.length"
        type="button"
        class="btn"
        @click="
          emit('update:tag', '');
          emit('update:tags', '');
        "
      >
        清除所选标签
      </button></label
    >
    <p>难度范围包含两端，例如“普及 → 普及+/提高−”。标签保持洛谷原生分类，多个标签取交集。</p>
    <p v-if="error" role="alert">
      {{ error }} <button class="btn" type="button" :disabled="busy" @click="load">重试分类</button>
    </p>
    <p v-else-if="!busy && !levels.length">原生分类尚未同步，已收录题目仍可浏览。</p>
    <p v-else-if="taxonomy.stale && !busy">分类信息待更新，暂用已保存的分类。</p>
  </div>
</template>
<style scoped>
.luogu-native-filters {
  display: flex;
  flex: 2 1 100%;
  gap: 16px;
  flex-wrap: wrap;
  min-width: 0;
  align-items: flex-end;
}
label {
  display: flex;
  flex: 1 1 155px;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
select {
  width: 100%;
  min-height: 44px;
  max-width: 100%;
  box-sizing: border-box;
}
.luogu-unrated {
  flex-direction: row;
  align-items: center;
  flex: 0 1 150px;
  min-height: 44px;
}
.luogu-unrated input {
  width: 20px;
  height: 20px;
}
.luogu-tags {
  flex-basis: 260px;
}
.luogu-tags select {
  min-height: 112px;
}
p {
  flex-basis: 100%;
  margin: 0;
  color: var(--muted, #697970);
  font-size: 12px;
  line-height: 1.8;
}
p[role='alert'] {
  color: var(--danger, #ad3f40);
}
</style>
