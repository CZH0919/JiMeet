/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: 'rgb(var(--rgb-primary) / <alpha-value>)',
          hover: 'rgb(var(--rgb-primary-hover) / <alpha-value>)',
          soft: 'rgb(var(--rgb-primary-soft) / <alpha-value>)',
        },
        success: 'rgb(var(--rgb-success) / <alpha-value>)',
        'success-soft': 'rgb(var(--rgb-success-soft) / <alpha-value>)',
        warning: 'rgb(var(--rgb-warning) / <alpha-value>)',
        'warning-soft': 'rgb(var(--rgb-warning-soft) / <alpha-value>)',
        danger: 'rgb(var(--rgb-danger) / <alpha-value>)',
        'danger-soft': 'rgb(var(--rgb-danger-soft) / <alpha-value>)',
        muted: 'rgb(var(--rgb-muted) / <alpha-value>)',
        'muted-soft': 'rgb(var(--rgb-muted-soft) / <alpha-value>)',
        page: 'rgb(var(--rgb-page) / <alpha-value>)',
        surface: 'rgb(var(--rgb-surface) / <alpha-value>)',
        line: 'rgb(var(--rgb-line) / <alpha-value>)',
        ink: 'rgb(var(--rgb-ink) / <alpha-value>)',
        ink2: 'rgb(var(--rgb-ink2) / <alpha-value>)',
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        pop: 'var(--shadow-pop)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(24px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'toast-in': {
          from: { opacity: '0', transform: 'translateY(-10px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.16s ease-out',
        'slide-in': 'slide-in 0.18s ease-out',
        'toast-in': 'toast-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
};
