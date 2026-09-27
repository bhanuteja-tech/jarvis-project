/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        carbon: '#0E1013',
        plate: '#16191E',
        steel: '#262B35',
        phosphor: '#E1E4EA',
        dim: '#828997',
        amber: {
          DEFAULT: '#D97736',
          muted: '#8A4518',
          glow: 'rgba(217, 119, 54, 0.15)',
        },
        sage: {
          DEFAULT: '#2EA069',
          muted: '#1A5A3B',
          glow: 'rgba(46, 160, 105, 0.15)',
        },
        crimson: {
          DEFAULT: '#E2604E',
          muted: '#7A281E',
          glow: 'rgba(226, 96, 78, 0.15)',
        },
        // Backwards-compatible mappings for existing views
        jarvis: {
          primary: '#D97736',
          secondary: '#828997',
          accent: '#2EA069',
          dark: '#16191E',
          darker: '#0E1013',
          surface: '#16191E',
          light: '#E1E4EA',
          muted: '#828997',
          border: '#262B35',
        },
      },
      fontFamily: {
        sans: ['"Instrument Sans"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      animation: {
        'signal-tick': 'signalTick 1.5s ease-in-out infinite',
      },
      keyframes: {
        signalTick: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
    },
  },
  plugins: [],
}

