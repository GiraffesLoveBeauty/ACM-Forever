import { createApp } from 'vue';
import App from './App.vue';
import router from './router.js';
import '../../api/acm_api/public/assets/app.css';
import '../../api/acm_api/public/assets/forum.css';
import '../../api/acm_api/public/assets/forum-graph.css';
import '../../api/acm_api/public/assets/forum-home-layout.css';
import '../../api/acm_api/public/assets/community-art.css';
import '../../api/acm_api/public/assets/admin.css';
import '../../api/acm_api/public/assets/cf-practice.css';
import '../../api/acm_api/public/assets/problem.css';
import '../../api/acm_api/public/assets/endfield-theme.css';
import './style.css';
import './post-layout.css';
import './forum-feedback.css';
import './wiki.css';
import './markdown-code.css';
import './statement-math.css';
import './header-layout.css';
import './training-tasks.css';
import './problem-presentation.css';
/* 主题：界面固定为 GitHub 风格骨架，四套配色见 themes.css / ThemeSwitcher.vue。
   主题类挂在 <html> 上（页面组件会整体重写 body.className）。 */
const THEMES = ['original', 'mist', 'forest', 'sand', 'ink'];
const DEFAULT_THEME = 'original';
let storedTheme = null;
try {
  storedTheme = localStorage.getItem('acm-theme');
} catch {
  storedTheme = null;
}
const theme = THEMES.includes(storedTheme) ? storedTheme : DEFAULT_THEME;
document.documentElement.classList.add('github-design');
document.documentElement.classList.add(`theme-${theme}`);
await import('./github-theme.css');
/* themes.css 必须在 github-theme.css 之后加载：基础层里有同名令牌的 !important 声明 */
await import('./themes.css');

const app = createApp(App);
const renderMath = (element) => window.renderForumMath?.(element);
app.directive('forum-math', { mounted: renderMath, updated: renderMath });
app.use(router).mount('#app');
