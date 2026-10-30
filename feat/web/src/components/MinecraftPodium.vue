<script setup>
// Original voxel podium; the numbers describe its three steps, not live leaderboard data.
const columns = [
  { x: 38, height: 1, label: '03' },
  { x: 123, height: 2, label: '02' },
  { x: 208, height: 3, label: '01' },
];
</script>
<template>
  <svg
    class="minecraft-podium"
    viewBox="0 0 320 190"
    role="img"
    aria-label="草地与泥土方块搭建的三级领奖台"
    focusable="false"
  >
    <path class="mc-podium-floor" d="M20 148l140 38 140-38M39 140l121 33 121-33" />
    <g v-for="column in columns" :key="column.label" class="mc-podium-column">
      <g
        v-for="level in column.height"
        :key="level"
        :transform="`translate(${column.x},${150 - level * 32})`"
        class="mc-podium-block"
      >
        <path class="mc-soil-front" d="M0 0l32 16v32L0 32Z" />
        <path class="mc-soil-side" d="M32 16L64 0v32L32 48Z" />
        <path
          :class="level === column.height ? 'mc-grass-top' : 'mc-podium-soil-top'"
          d="M0 0l32-16L64 0 32 16Z"
        />
        <path
          v-if="level === column.height"
          class="mc-grass-edge"
          d="M0 0l32 16L64 0v8L32 24 0 8Z"
        />
        <path
          class="mc-soil-flecks"
          d="M7 15l7 3v6l-7-3ZM21 29l6 3v7l-6-3ZM39 28l7-3v6l-7 3ZM53 13l6-3v5l-6 3Z"
        />
        <path
          v-if="level === column.height"
          class="mc-podium-grass-flecks"
          d="M10-1l7-4 7 4-7 4ZM38-4l6-3 8 4-6 3Z"
        />
      </g>
      <text :x="column.x + 32" :y="130 - column.height * 32" class="mc-podium-rank">
        {{ column.label }}
      </text>
    </g>
  </svg>
</template>
