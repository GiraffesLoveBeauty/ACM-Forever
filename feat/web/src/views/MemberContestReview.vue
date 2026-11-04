<script setup>
import ContestReviewPanel from '../components/ContestReviewPanel.vue';
</script>
<template>
  <main class="community-main member-contest-review">
    <RouterLink class="forum-back-link" to="/home.html">← 返回个人中心</RouterLink>
    <h1>赛事复盘</h1>
    <p>查看本人的比赛题目记录，标记补题与复盘进度。</p>
    <ContestReviewPanel personal />
  </main>
</template>
