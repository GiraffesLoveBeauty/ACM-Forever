// Reuse the actual repository components and styles. No re-traced artwork or remote code.
import {createApp, h, reactive} from '../../feat/web/node_modules/vue/dist/vue.esm-bundler.js';
import GraphArt from '../../feat/web/src/components/GraphArt.vue';
import CommunityArt from '../../feat/web/src/components/CommunityArt.vue';
import {deriveTokens} from '../../feat/web/src/lib/theme-colors.js';
import '../../feat/api/acm_api/public/assets/app.css';
import '../../feat/api/acm_api/public/assets/forum-graph.css';
import '../../feat/api/acm_api/public/assets/community-art.css';
import '../../feat/api/acm_api/public/assets/endfield-theme.css';
import '../../feat/web/src/style.css';
import '../../feat/web/src/phase-theme.css';
import '../../feat/web/src/angel-city-theme.css';
import '../../feat/web/src/minecraft-theme.css';
import './mobile.css';

const state=reactive({scene:'background',design:'original'});
const app=createApp({setup(){return ()=>state.scene==='background'?null:h('section',{class:'forum-welcome'},[state.scene==='graph'?h(GraphArt):h(CommunityArt,{scene:state.scene})]);}});
app.provide('getDesignTemplate',()=>state.design);
app.mount('#app');
window.applyTheme=(config)=>{
  state.design=config.design;state.scene=config.scene;
  document.documentElement.dataset.designTemplate=config.design;
  document.documentElement.dataset.customTheme='true';
  document.documentElement.dataset.theme=config.dark?'dark':'light';
  document.body.dataset.mobileScene=config.scene;
  for(const [key,value] of Object.entries(deriveTokens(config.profile,config.dark)))document.body.style.setProperty(key,value);
};
