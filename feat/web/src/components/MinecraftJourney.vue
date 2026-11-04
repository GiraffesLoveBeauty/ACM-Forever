<script setup>
// Original voxel workshop and pixel trail, drawn without game textures.
const tiles = [
  [42, 116],
  [90, 140],
  [138, 116],
  [186, 140],
  [234, 116],
  [90, 92],
  [138, 68],
  [186, 92],
];
</script>
<template>
  <svg
    class="minecraft-journey"
    viewBox="0 0 340 220"
    role="img"
    aria-label="工作台、像素镐和连接草地方块的探索小径"
    focusable="false"
  >
    <g class="mc-journey-terrain" stroke-linejoin="miter">
      <g v-for="([x, y], i) in tiles" :key="i" :transform="`translate(${x},${y})`">
        <path class="mc-soil-front" d="M0 0l24 12v24L0 24Z" />
        <path class="mc-soil-side" d="M24 12L48 0v24L24 36Z" />
        <path class="mc-grass-top" d="M0 0l24-12L48 0 24 12Z" />
        <path class="mc-grass-edge" d="M0 0l24 12L48 0v6L24 18 0 6Z" />
        <path class="mc-soil-flecks" d="M6 11l6 3v5l-6-3ZM16 21l5 2v5l-5-2ZM30 24l6-3v5l-6 3Z" />
      </g>
      <path
        class="mc-journey-trail"
        d="M104 132l12-6 8 4-12 6ZM130 119l12-6 8 4-12 6ZM156 106l12-6 8 4-12 6ZM182 119l12-6 8 4-12 6ZM208 132l12-6 8 4-12 6Z"
      />
      <g transform="translate(65,95)">
        <path class="mc-trunk-front" d="M0 0l24 12v25L0 25Z" />
        <path class="mc-trunk-side" d="M24 12L48 0v25L24 37Z" />
        <path class="mc-bench-top" d="M0 0l24-12L48 0 24 12Z" />
        <path
          class="mc-bench-grid"
          d="M8-4l24 12M16-8l24 12M8 4l24-12M16 8L40-4M8 8v17M17 13v17M31 13v17M40 8v17"
        />
      </g>
    </g>
    <g class="mc-journey-pickaxe" transform="translate(210,34)">
      <path
        class="mc-journey-handle"
        d="M0 61h8v-8h8v-8h8v-8h8v-8h8v-8h8v16h-8v8h-8v8h-8v8h-8v8H0Z"
      />
      <path class="mc-journey-tool-edge" d="M10 0h40v8h8v8h8v8h8v32H58V32h-8v-8h-8v-8H10Z" />
      <path class="mc-journey-tool" d="M18 8h24v8h8v8h8v8h8v16h-8V32h-8v-8h-8v-8H18Z" />
      <path class="mc-journey-tool-glint" d="M18 8h24v8H18ZM58 32h8v16h-8Z" />
    </g>
    <g class="mc-sparks">
      <path d="M52 40h5v-5h5v5h5v5h-5v5h-5v-5h-5ZM284 162h5v-5h5v5h5v5h-5v5h-5v-5h-5Z" />
    </g>
  </svg>
</template>
