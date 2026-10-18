import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';

// Public, synthetic fixture only. Never point this config at PANAM production.
const app = {
  url: 'http://127.0.0.1:4317',
  command: {
    executable: 'node',
    args: ['server.mjs'],
    log: '.e2e/logs/app.log',
  },
};

export default {
  tests: 'tests/**/*.e2e.ts',
  retries: 0,
  timeout: 45000,
  targets: [
    { name: 'desktop', engine: web({ viewport: { width: 1280, height: 800 } }), app },
    { name: 'mobile-width', engine: web({ viewport: { width: 390, height: 844 } }), app },
  ],
} satisfies E2EConfig;
