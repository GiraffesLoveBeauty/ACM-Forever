<script setup>
import TrainingPanel from '../components/TrainingPanel.vue';
</script>
<template>
  <main class="community-main member-training">
    <RouterLink class="forum-back-link" to="/home.html">← 返回个人中心</RouterLink>
    <h1>今日训练</h1>
    <p>为自己生成不同难度的训练题，并查看本人的挑战历史。</p>
    <TrainingPanel personal />
  </main>
</template>
