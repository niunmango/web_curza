/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        uncoma: {
          navy: '#003366',       // Azul institucional primario UNComa
          dark: '#002244',       // Azul noche para footers y barras
          slate: '#153D66',      // Azul pizarra intermedio
          blue: '#01579B',       // Azul medio de interacción
          sky: '#6EC1E4',        // Azul cielo de acento
          ice: '#F0F5FA',        // Fondo suave institucional
          gold: '#F39200',       // Dorado / Ámbar institucional UNComa
          lightGold: '#FFBC7D',  // Ámbar claro
          text: '#313131',       // Texto oscuro principal
          muted: '#545454'       // Texto secundario
        }
      },
      fontFamily: {
        sans: ['Poppins', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      }
    },
  },
  plugins: [],
};
