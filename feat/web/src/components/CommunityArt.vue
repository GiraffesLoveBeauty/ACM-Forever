<script setup>
defineProps({ scene: { type: String, default: 'podium' } });
</script>
<template>
  <figure
    class="community-header-art"
    :aria-label="scene === 'podium' ? '立体 AC 阶梯' : '解题轨迹'"
  >
    <div class="header-art-layer">
      <svg
        class="header-art-scene"
        viewBox="0 0 320 190"
        role="img"
        :aria-label="scene === 'podium' ? '不断进步的解题过程' : '从思考到 AC 的轨迹'"
      >
        <template v-if="scene === 'podium'">
          <path d="M26 141L141 172L301 140M53 126L166 153L280 128" class="header-art-floor" />
          <path d="M93 83Q154 47 218 25" class="header-art-route" />
          <g
            v-for="([x, top, label], i) in [
              [79, 96, '03'],
              [141, 66, '02'],
              [210, 38, '01'],
            ]"
            :key="i"
            class="header-art-step"
          >
            <path :d="`M${x} ${top}l41 -11 27 14 -40 12Z`" class="header-art-step-top" />
            <path :d="`M${x} ${top}l28 15v${137 - top}l-28 -14Z`" class="header-art-step-front" />
            <path
              :d="`M${x + 28} ${top + 15}l40 -12v${137 - top}l-40 12Z`"
              class="header-art-step-side"
            />
            <text :x="x + 24" :y="top - 21" class="header-art-rank">{{ label }}</text>
          </g>
        </template>
        <template v-else>
          <path
            d="M44 143Q97 28 167 107T294 58M49 156Q97 41 168 120T294 71"
            class="header-art-traces"
          />
          <path d="M44 128Q96 11 164 92T287 42" class="header-art-route" />
          <g
            v-for="([x, y, label], i) in [
              [73, 76, 'think'],
              [164, 92, 'code'],
              [287, 42, 'AC'],
            ]"
            :key="i"
            class="header-art-node"
          >
            <circle :cx="x" :cy="y" r="21" class="header-art-halo" />
            <circle :cx="x" :cy="y" r="7" class="header-art-dot" />
            <text :x="x" :y="y - 19">{{ label }}</text>
          </g>
          <text x="205" y="166" class="header-art-note">one step at a time</text>
        </template></svg
      ><span class="header-art-caption" aria-hidden="true">AC · keep climbing</span>
    </div>
  </figure>
</template>
