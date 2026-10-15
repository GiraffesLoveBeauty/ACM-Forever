import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve, relative, sep, extname } from 'node:path';
import { cpSync, mkdirSync, createReadStream, existsSync, readFileSync, writeFileSync } from 'node:fs';

// Shared public assets keep their historical URLs; legacy HTML pages are not part of the Vue build.
const media = ['icpc-logo.png', 'default-avatar.png', 'hero-halftone.svg'];
export default defineConfig({
  plugins: [
    vue({ template: { transformAssetUrls: false } }),
    {
      name: 'community-media',
      enforce: 'pre',
      transform(source, id) {
        // Resolve the shared CSS artwork from its source directory in Vite.
        if (id.split('?')[0].endsWith('/endfield-theme.css'))
          return source.replaceAll("'/assets/hero-halftone.svg'", "'./hero-halftone.svg'");
      },
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const pathname = req.url?.split('?')[0] || '';
          if (!pathname.startsWith('/assets/')) return next();
          const assetRoot = resolve('../api/acm_api/public');
          const assetPath = resolve(assetRoot, pathname.slice(1));
          const assetRelative = relative(assetRoot, assetPath);
          if (
            !assetRelative || assetRelative.startsWith(`..${sep}`) || assetRelative === '..' ||
            !existsSync(assetPath)
          ) return next();
          const contentTypes = {
            '.css': 'text/css; charset=utf-8',
            '.js': 'text/javascript; charset=utf-8',
            '.otf': 'font/otf',
            '.png': 'image/png',
            '.svg': 'image/svg+xml',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
          };
          res.setHeader('Content-Type', contentTypes[extname(assetPath)] || 'application/octet-stream');
          createReadStream(assetPath).pipe(res);
        });
      },
      closeBundle() {
        mkdirSync('dist/assets', { recursive: true });
        for (const file of media)
          cpSync(resolve('../api/acm_api/public/assets', file), resolve('dist/assets', file));
        const html = readFileSync('dist/index.html', 'utf8');
        writeFileSync(
          'dist/retired.html',
          html.replace(
            '请启用 JavaScript 访问 ACM Forever。',
            '功能已下线，历史资料保留存档。请启用 JavaScript 查看当前入口。',
          ),
        );
      },
    },
  ],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      ['/api', '/uploads', '/health'].map((path) => [path, 'http://127.0.0.1:8088']),
    ),
    fs: { allow: [resolve('..')] },
  },
  build: { target: 'es2022' },
});
