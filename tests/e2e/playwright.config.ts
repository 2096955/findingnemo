import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 600000,
  retries: 0,
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
