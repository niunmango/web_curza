/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        curza: {
          blue: '#003366',
          lightBlue: '#0055a5',
          gold: '#c69214',
          gray: '#f4f6f9'
        }
      }
    },
  },
  plugins: [],
};
