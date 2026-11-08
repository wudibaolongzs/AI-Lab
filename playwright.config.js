const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser',
  use: { baseURL: 'http://127.0.0.1:8020', browserName: 'chromium',
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) },
  webServer: {
    command: 'python -B app.py --port 8020',
    url: 'http://127.0.0.1:8020', reuseExistingServer: false,
    env: { BAIDU_OCR_ENABLED: '0', AI_PROVIDER: 'agentarts', AGENTARTS_API_KEY: '', TENCENT_API_KEY: '', DEEPSEEK_API_KEY: '' }
  }
});
