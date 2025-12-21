/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        spine: {
          50: '#f0f7ff',
          100: '#e0efff',
          200: '#b9dfff',
          300: '#7cc5ff',
          400: '#36a9ff',
          500: '#0c8ff0',
          600: '#0070cc',
          700: '#0059a5',
          800: '#054b88',
          900: '#0a3f70',
          950: '#07284a',
        },
      },
    },
  },
  plugins: [],
};
