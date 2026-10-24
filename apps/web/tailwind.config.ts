import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0d1117',
        panel: '#171b22',
        accent: '#f59e0b',
        mist: '#e6e7eb',
        muted: '#8b92a7',
      },
      boxShadow: {
        panel: '0 10px 30px rgba(15, 23, 42, 0.18)',
      },
    },
  },
  plugins: [],
};

export default config;
