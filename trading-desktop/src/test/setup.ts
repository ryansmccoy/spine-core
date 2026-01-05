import '@testing-library/jest-dom';

// Mock environment variables
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_MARKET_SPINE_URL: 'http://localhost:8000',
    VITE_ENABLE_TRACING: 'true',
  },
  writable: true,
});
