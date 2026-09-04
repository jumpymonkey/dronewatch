/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          bg: '#0B0F17',
          card: '#131A26',
          border: '#212D40',
          accent: '#1E293B'
        }
      },
      animation: {
        'pulse-glow': 'pulseGlow 1.5s infinite alternate',
      },
      keyframes: {
        pulseGlow: {
          '0%': { boxShadow: '0 0 10px rgba(239, 68, 68, 0.4)' },
          '100%': { boxShadow: '0 0 25px rgba(239, 68, 68, 0.9)' },
        }
      }
    },
  },
  plugins: [],
}
