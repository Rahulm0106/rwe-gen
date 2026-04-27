/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'secondary': '#006a61',
        'on-secondary': '#ffffff',
        'on-background': '#0b1c30',
        'on-primary-container': '#7c839b',
        'primary-container': '#131b2e',
        'surface': '#f8f9ff',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

