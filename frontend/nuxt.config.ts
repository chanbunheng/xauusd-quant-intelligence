// Nuxt 4 Configuration for XAU/USD Quantitative AI Intelligence Platform
export default defineNuxtConfig({
  future: {
    compatibilityVersion: 4,
  },
  ssr: false,
  devtools: { enabled: true },
  app: {
    head: {
      title: 'AurumQuant AI — Institutional XAU/USD Trading & Intelligence Platform',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        {
          name: 'description',
          content: 'Institutional XAU/USD AI Trading Terminal powered by a 3-Agent Committee, TradingView Feeds, Supabase PostgreSQL, and Railway 24/7 Execution.',
        },
      ],
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap',
        },
      ],
    },
  },
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'https://gold-signal-api-production.up.railway.app',
      supabaseUrl: process.env.NUXT_PUBLIC_SUPABASE_URL || 'https://cpotlpgymbgfqhedbmrb.supabase.co',
    },
  },
})
