<script setup>
import { ref, computed } from 'vue';
const points = [
  { id: 's', x: 50, y: 151 },
  { id: 'u', x: 114, y: 83 },
  { id: 'a', x: 177, y: 47 },
  { id: 'b', x: 248, y: 63 },
  { id: 'c', x: 323, y: 96 },
  { id: 't', x: 348, y: 174 },
  { id: 'v', x: 198, y: 130 },
  { id: 'd', x: 256, y: 167 },
  { id: 'e', x: 285, y: 232 },
  { id: 'f', x: 155, y: 215 },
  { id: 'g', x: 84, y: 227 },
  { id: 'h', x: 312, y: 32 },
];
const edges = [
  ['s', 'u', 7],
  ['s', 'v', 3],
  ['s', 'g', 10],
  ['u', 'a', 4],
  ['u', 'v', 6],
  ['a', 'b', 8],
  ['a', 'h', 13],
  ['b', 'c', 7],
  ['b', 'v', 9],
  ['c', 't', 8],
  ['c', 'h', 3],
  ['v', 'd', 2],
  ['v', 'f', 6],
  ['d', 't', 4],
  ['d', 'e', 7],
  ['f', 'e', 8],
  ['f', 'g', 4],
  ['g', 'e', 16],
  ['e', 't', 9],
  ['b', 'd', 9],
  ['h', 't', 16],
];
const byId = Object.fromEntries(points.map((p) => [p.id, p])),
  distances = Object.fromEntries(points.map((p) => [p.id, Infinity])),
  previous = {},
  remaining = new Set(points.map((p) => p.id));
distances.s = 0;
while (remaining.size) {
  const current = [...remaining].sort((a, b) => distances[a] - distances[b])[0];
  remaining.delete(current);
  for (const [a, b, weight] of edges) {
    const next = a === current ? b : b === current ? a : null;
    if (next && remaining.has(next) && distances[current] + weight < distances[next]) {
      distances[next] = distances[current] + weight;
      previous[next] = current;
    }
  }
}
const selected = ref('t'),
  hovered = ref(null);
const target = computed(() => hovered.value || selected.value);
const route = computed(() => {
  const result = [];
  for (let p = target.value; p; p = previous[p]) result.unshift(p);
  return result;
});
const path = computed(() =>
  route.value.map((id, i) => `${i ? 'L' : 'M'}${byId[id].x},${byId[id].y}`).join(' '),
);
const activeEdges = computed(
  () => new Set(route.value.slice(1).map((id, i) => [route.value[i], id].sort().join(':'))),
);
</script>
<template>
  <figure class="forum-algorithm-art" aria-label="空间算法图谱">
    <div class="algorithm-disc" aria-hidden="true"></div>
    <div class="algorithm-square" aria-hidden="true"></div>
    <div class="algorithm-slice" aria-hidden="true"></div>
    <div class="algorithm-arch" aria-hidden="true"></div>
    <div class="algorithm-aura" aria-hidden="true"></div>
    <div class="algorithm-layer">
      <div class="algorithm-grid" aria-hidden="true"></div>
      <svg
        class="algorithm-graph"
        viewBox="0 0 400 300"
        role="group"
        aria-label="十二节点最短路径图"
        @keydown.esc="selected = 't'"
      >
        <g class="graph-floor" transform="translate(0,20)" aria-hidden="true">
          <line
            v-for="([a, b], i) in edges"
            :key="i"
            class="graph-floor-edge"
            :x1="byId[a].x"
            :y1="byId[a].y"
            :x2="byId[b].x"
            :y2="byId[b].y"
          />
          <circle
            v-for="p in points"
            :key="p.id"
            class="graph-floor-node"
            :cx="p.x"
            :cy="p.y"
            :r="route.includes(p.id) ? 5 : 3"
          />
        </g>
        <g v-for="([a, b, w], i) in edges" :key="i" aria-hidden="true">
          <line
            class="graph-edge"
            :x1="byId[a].x"
            :y1="byId[a].y"
            :x2="byId[b].x"
            :y2="byId[b].y"
          />
          <text
            v-if="
              activeEdges.has([a, b].sort().join(':')) ||
              ['a:u', 'b:c', 'c:h', 'e:f'].includes([a, b].sort().join(':'))
            "
            class="graph-weight"
            :x="(byId[a].x + byId[b].x) / 2"
            :y="(byId[a].y + byId[b].y) / 2 - 7"
          >
            {{ w }}
          </text>
        </g>
        <path class="graph-path-haze" :d="path" />
        <path class="graph-path-core" :d="path" />
        <g
          v-for="p in points"
          :key="p.id"
          class="graph-node"
          :class="{ 'is-path': route.includes(p.id), 'is-hover': hovered === p.id }"
          role="button"
          tabindex="0"
          :aria-label="`节点 ${p.id}，最短距离 ${distances[p.id]}`"
          :aria-pressed="selected === p.id"
          @pointerenter="hovered = p.id"
          @pointerleave="hovered = null"
          @focus="hovered = null"
          @click="
            selected = p.id;
            hovered = null;
          "
          @keydown.enter.prevent="selected = p.id"
          @keydown.space.prevent="selected = p.id"
        >
          <circle class="graph-node-hit" :cx="p.x" :cy="p.y" r="22" />
          <circle class="graph-node-ring" :cx="p.x" :cy="p.y" r="14" />
          <circle
            :class="route.includes(p.id) ? 'graph-node-front' : 'graph-node-back'"
            :cx="p.x"
            :cy="p.y"
            :r="route.includes(p.id) ? 9 : 6"
          />
          <text
            :class="route.includes(p.id) ? 'graph-node-label' : 'graph-node-label-secondary'"
            :x="p.x"
            :y="route.includes(p.id) ? p.y : p.y - 14"
          >
            {{ p.id }}
          </text>
        </g>
        <g aria-hidden="true">
          <path class="graph-ring-arc" d="M320 127A46 46 0 0 1 380 185" />
          <path class="graph-callout-line" d="M348 184L343 208L310 208" />
          <rect class="graph-callout-surface" x="300" y="202" width="67" height="23" rx="5" />
          <text class="graph-callout-text" x="313" y="218">✓ AC</text>
          <text class="graph-trace-caption" x="81" y="274">
            dist[{{ target }}] = {{ distances[target] }};
          </text>
        </g></svg
      ><span class="graph-status graph-sr-only" role="status"
        >{{ route.join(' → ') }}，权重 {{ distances[target] }}</span
      ><span class="algorithm-code">dist[{{ target }}] = {{ distances[target] }};</span>
    </div>
    <figcaption>最短路径图谱 / 点选节点探索</figcaption>
  </figure>
</template>
