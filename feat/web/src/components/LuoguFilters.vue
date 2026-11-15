<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRequests } from '../lib/api.js';
const props = defineProps({
  difficulty: { type: String, default: '' },
  tag: { type: String, default: '' },
});
const emit = defineEmits(['update:difficulty', 'update:tag']);
const request = useRequests(),
  taxonomy = ref({ difficulties: [], tags: [], tag_types: [] }),
  busy = ref(false),
  error = ref('');
const levels = computed(() => taxonomy.value.difficulties || []);
const tags = computed(() => taxonomy.value.tags || []);
const groups = computed(() => {
  const result = new Map();
  for (const tag of tags.value) {
    const category =
      (taxonomy.value.tag_types || []).find((type) => type.id === tag.type)?.name || '其他标签';
    if (!result.has(category)) result.set(category, []);
    result.get(category).push(tag);
  }
  return [...result].map(([name, items]) => ({ name, items }));
});
const unknownLevel = computed(
  () =>
    props.difficulty !== '' && !levels.value.some((item) => String(item.id) === props.difficulty),
);
const unknownTag = computed(
  () => props.tag !== '' && !tags.value.some((item) => String(item.id) === props.tag),
);
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
      ><span>洛谷难度</span
      ><select
        :value="difficulty"
        :disabled="busy"
        @change="emit('update:difficulty', $event.target.value)"
      >
        <option value="">{{ busy ? '正在加载难度…' : '全部原生难度' }}</option>
        <option v-if="unknownLevel" :value="difficulty">
          难度 #{{ difficulty }}（名称待更新）
        </option>
        <option v-for="level in levels" :key="level.id" :value="String(level.id)">
          {{ level.name }}
        </option>
      </select></label
    >
    <label
      ><span>洛谷原生标签</span
      ><select :value="tag" :disabled="busy" @change="emit('update:tag', $event.target.value)">
        <option value="">{{ busy ? '正在加载标签…' : '全部原生标签' }}</option>
        <option v-if="unknownTag" :value="tag">标签 #{{ tag }}（名称待更新）</option>
        <optgroup v-for="group in groups" :key="group.name" :label="group.name">
          <option v-for="item in group.items" :key="item.id" :value="String(item.id)">
            {{ item.name }}
          </option>
        </optgroup>
      </select></label
    >
    <p v-if="error" role="alert">
      {{ error }} <button class="btn" type="button" :disabled="busy" @click="load">重试分类</button>
    </p>
    <p v-else-if="!busy && !levels.length">原生分类尚未同步，已收录题目仍可浏览。</p>
    <p v-else-if="taxonomy.stale && !busy" class="luogu-taxonomy-note">
      分类信息待更新，暂用已保存的分类。
    </p>
  </div>
</template>
<style scoped>
.luogu-native-filters {
  display: flex;
  flex: 2 1 360px;
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
