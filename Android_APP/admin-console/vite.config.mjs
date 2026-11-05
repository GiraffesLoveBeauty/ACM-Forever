import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve, dirname } from 'node:path';
import { readFileSync, writeFileSync, mkdirSync, readdirSync, copyFileSync } from 'node:fs';
const root = dirname(fileURLToPath(import.meta.url));
const require = createRequire(resolve(root, '../../feat/web/package.json'));
const { default: vue } = await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')));
let runtimeModules=[];
export default {
  root, base: './', plugins: [vue({ template: { transformAssetUrls: false } }),{
    name:'mobile-admin-artifact',generateBundle(_,bundle){runtimeModules=Object.values(bundle).filter(item=>item.type==='chunk').flatMap(item=>Object.entries(item.modules).filter(([,value])=>value.renderedLength>0).map(([name])=>name));},closeBundle(){
      const output=resolve(root,'../app/app/src/main/assets/admin'), index=resolve(output,'index.html');
      writeFileSync(index,readFileSync(index,'utf8').replace('type="module"','defer').replaceAll(' crossorigin',''));
      mkdirSync(resolve(output,'licenses'),{recursive:true});
      const notices=[];
      for(const name of ['vue','vue-router','@vue/runtime-core','@vue/runtime-dom','@vue/reactivity','@vue/shared','@vue/devtools-api','marked','dompurify']){
        if(!runtimeModules.some(file=>file.replaceAll('\\','/').includes('/node_modules/'+name+'/')))continue;
        let directory;
        try{directory=dirname(require.resolve(name));}catch{
          const packages=resolve(root,'../../feat/web/node_modules/.pnpm');
          const entry=readdirSync(packages).find(value=>value.startsWith(name.replace('/','+')+'@'));
          if(!entry)throw Error('Missing runtime license package: '+name);
          directory=resolve(packages,entry,'node_modules',name);
        }
        while(dirname(directory)!==directory){
          try{const info=JSON.parse(readFileSync(resolve(directory,'package.json'),'utf8'));if(info.name===name){
            const license=readdirSync(directory).find(file=>/^LICENSE(?:\.|$)/i.test(file));
            if(!license)throw Error('Missing license: '+name);
            const filename=name.replaceAll('/','_').replace('@','')+'-'+license;
            copyFileSync(resolve(directory,license),resolve(output,'licenses',filename));notices.push(name+' '+info.version+' — '+filename);break;
          }}catch(error){if(error.message.startsWith('Missing license:'))throw error;}
          directory=dirname(directory);
        }
      }
      writeFileSync(resolve(output,'THIRD_PARTY_NOTICES.txt'),'Runtime third-party licenses\n'+notices.join('\n')+'\n');
    }
  }],
  resolve: { alias: { vue: require.resolve('vue/dist/vue.runtime.esm-bundler.js'), 'vue-router': require.resolve('vue-router/dist/vue-router.mjs') } },
  build: { target: 'es2020', outDir: resolve(root, '../app/app/src/main/assets/admin'), emptyOutDir: true,rollupOptions:{output:{format:'iife',inlineDynamicImports:true}} },
};
