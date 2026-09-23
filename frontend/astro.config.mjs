import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import node from '@astrojs/node';

const siteUrl = process.env.PUBLIC_SITE_URL || process.env.SITE_URL || 'http://air.local:8888';

// https://astro.build/config
export default defineConfig({
  site: siteUrl,
  output: 'hybrid',
  adapter: node({
    mode: 'standalone',
  }),
  devToolbar: {
    enabled: false,
  },
  integrations: [tailwind()],
  server: {
    host: '0.0.0.0',
    port: 4321
  },
  vite: {
    server: {
      allowedHosts: true
    }
  }
});
