<script setup>
// Original architectural linework; no game images or remote resources.
const contours = Array.from({ length: 19 }, (_, index) => {
  const offset = index * 4.5;
  return `M${68 + offset} 220 C${165 + offset * 0.35} 220 ${170 + offset * 0.4} 195 ${190 + offset * 0.22} 121 C${203 + offset * 0.15} 72 ${219 + offset * 0.1} ${31 + offset * 0.25} 240 ${17 + offset * 0.3} C${263 - offset * 0.1} ${31 + offset * 0.25} ${277 - offset * 0.15} 72 ${290 - offset * 0.22} 121 C${310 - offset * 0.4} 195 ${315 - offset * 0.35} 220 ${412 - offset} 220`;
});
</script>

<template>
  <svg class="angel-city-art" viewBox="0 0 480 360" aria-hidden="true" focusable="false">
    <g class="angel-city-grid">
      <path v-for="n in 9" :key="`x-${n}`" :d="`M${n * 48} 20V340`" />
      <path v-for="n in 7" :key="`y-${n}`" :d="`M16 ${n * 44}H464`" />
    </g>
    <g class="angel-city-skyline">
      <path
        d="M15 220V200H30V181H41V204H54V171H67V220H89V188H105V161H118V220H148V193H168V205H180V220M304 220V202H322V171H336V155H343V171H355V220H378V186H396V202H410V167H424V186H440V205H466V220"
      />
    </g>
    <path
      class="angel-city-temple-fill"
      d="M68 220C172 220 172 195 190 121C205 65 221 31 240 17C263 31 277 72 290 121C308 195 308 220 412 220Z"
    />
    <g class="angel-city-contours">
      <path v-for="(path, i) in contours" :key="i" :d="path" />
    </g>
    <g class="angel-city-reflection" transform="translate(0 350) scale(1 -.59)">
      <path v-for="(path, i) in contours" :key="i" :d="path" />
    </g>
    <g class="angel-city-axis">
      <path d="M16 220H468M240 350V5M12 220L24 215M12 220L24 225M240 5L235 17M240 5L245 17" />
      <path v-for="n in 8" :key="n" :d="`M${n * 52} 216V224`" />
      <path v-for="n in 7" :key="`v-${n}`" :d="`M236 ${n * 44}H244`" />
      <path d="M54 49H150V97H54ZM306 40H427V85H306ZM71 280H114V331H71Z" />
      <path d="M54 44V54M49 49H59M145 97H155M150 92V102M301 40H311M306 35V45" />
      <circle v-for="n in 5" :key="`ring-${n}`" cx="34" :cy="n * 32 + 35" r="13" />
      <path d="M34 47V208M320 277H442V322H320Z" stroke-dasharray="4 5" />
    </g>
    <g class="angel-city-insets">
      <path
        d="M59 91V80H67V75H74V89H86V81H93V70H99V83H106V91H143M94 90Q101 61 108 57Q116 62 123 90M99 90Q104 69 108 65Q113 70 118 90"
      />
      <path d="M310 77Q325 61 342 68Q351 49 373 60Q392 48 412 65L423 69V80Z" />
      <path
        d="M310 83Q333 76 352 79Q382 67 423 75M77 325L105 288L88 315L108 302M78 316L105 288L94 324"
      />
    </g>
    <g class="angel-city-fragments">
      <path d="M50 273L174 244L117 269L87 317L98 279Z" />
      <path d="M340 136L443 111L382 144L351 190L359 151Z" />
      <path d="M79 115L89 127L108 116L90 136Z M366 66L374 74L389 64L376 82Z" />
    </g>
    <g class="angel-city-typesetting">
      <text x="18" y="28">CITY OF ANGELS</text>
      <text x="250" y="18">Y</text>
      <text x="449" y="211">X</text>
      <text x="250" y="235">0,0</text>
      <text x="320" y="310">CONNECT / THINK</text>
    </g>
  </svg>
</template>
