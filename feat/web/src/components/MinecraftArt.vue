<script setup>
// Original voxel illustration. No game textures, fonts or third-party assets.
const blocks = [
  [56, 258, 48],
  [104, 282, 48],
  [152, 258, 48],
  [200, 282, 48],
  [248, 258, 48],
  [296, 282, 48],
  [104, 234, 48],
  [152, 210, 48],
  [200, 234, 48],
  [248, 210, 48],
];
</script>
<template>
  <svg class="minecraft-art" viewBox="0 0 400 360" aria-hidden="true" focusable="false">
    <g class="mc-clouds">
      <path d="M16 44h18V32h38v12h24v14H16ZM277 21h22V9h42v12h35v15h-99Z" />
      <path d="M328 120h16v-12h26v12h20v10h-62Z" />
    </g>
    <g class="mc-landscape" stroke-linejoin="miter" stroke-width="1.5">
      <g v-for="([x, y, size], i) in blocks" :key="i" :transform="`translate(${x},${y})`">
        <path class="mc-soil-front" :d="`M0 0l${size} 24v42L0 42Z`" />
        <path class="mc-soil-side" :d="`M${size} 24l${size} -24v42l-${size} 24Z`" />
        <path class="mc-grass-top" :d="`M0 0l${size} -24l${size} 24l-${size} 24Z`" />
        <path class="mc-grass-edge" :d="`M0 0l${size} 24l${size} -24v9l-${size} 24L0 9Z`" />
        <path class="mc-soil-flecks" d="M10 18l9 4v6l-9-4ZM30 36l7 3v5l-7-3ZM64 38l9-4v6l-9 4Z" />
      </g>
      <g transform="translate(278,209)">
        <path class="mc-trunk-front" d="M0 0l12 6v-58L0-58Z" />
        <path class="mc-trunk-side" d="M12 6l12-6v-58l-12 6Z" />
        <path class="mc-leaves-side" d="M-22-54l36 18l42-21v-37L14-73l-36-18Z" />
        <path class="mc-leaves-top" d="M-22-91l42-21l36 18l-42 21Z" />
        <path class="mc-leaves-shade" d="M14-73l42-21v37L14-36Z" />
        <path
          class="mc-leaves-detail"
          d="M-10-78l12 6v10l-12-6ZM25-92l10-5l11 5l-10 5ZM25-59l12-6v10l-12 6Z"
        />
      </g>
      <g class="mc-workbench" transform="translate(109,225)">
        <path class="mc-trunk-front" d="M0 0l26 13v25L0 25Z" />
        <path class="mc-trunk-side" d="M26 13L52 0v25L26 38Z" />
        <path class="mc-bench-top" d="M0 0l26-13L52 0L26 13Z" />
        <path
          class="mc-bench-grid"
          d="M9-4l26 13M17-9l26 13M9 4l26-13M17 9L43-4M7 8v16M20 15v16M33 15v16M45 8v16"
        />
      </g>
    </g>
    <g class="mc-sparks">
      <path d="M40 176h5v-5h5v5h5v5h-5v5h-5v-5h-5ZM354 211h4v-4h4v4h4v4h-4v4h-4v-4h-4Z" />
    </g>
  </svg>
</template>
