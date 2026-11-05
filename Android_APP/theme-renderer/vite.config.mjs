import {defineConfig} from '../../feat/web/node_modules/vite/dist/node/index.js';
import vue from '../../feat/web/node_modules/@vitejs/plugin-vue/dist/index.mjs';
import {fileURLToPath} from 'node:url';
export default defineConfig({root:fileURLToPath(new URL('.',import.meta.url)),base:'./',plugins:[vue()],resolve:{alias:[{find:'vue',replacement:fileURLToPath(new URL('../../feat/web/node_modules/vue/dist/vue.esm-bundler.js',import.meta.url))},{find:'/assets/hero-halftone.svg',replacement:fileURLToPath(new URL('../../feat/api/acm_api/public/assets/hero-halftone.svg',import.meta.url))}]},build:{outDir:'../app/app/src/main/assets/themes/renderer',emptyOutDir:true,minify:true,cssCodeSplit:false}});
