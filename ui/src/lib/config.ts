/**
 * Application configuration
 * For local development, API runs on localhost:8001
 */

export const config = {
  api: {
    baseUrl: process.env.NODE_ENV === 'production' 
      ? 'http://localhost:8001' // Could be changed for production
      : 'http://localhost:8001', // Local development
  },
  app: {
    name: 'PMM Companion',
    version: '1.0.0',
  },
} as const;

export default config;
