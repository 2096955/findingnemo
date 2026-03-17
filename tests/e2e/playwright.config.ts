import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 180000,
  retries: 1,
  use: {
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
