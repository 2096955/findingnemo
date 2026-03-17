import { test, expect } from "@playwright/test";

const BASE_URL =
  process.env.WHALE_AGENT_URL ||
  "https://whale-agent-534348290993.us-central1.run.app";

test.describe("Whale Agent Live Smoke Tests", () => {
  test("homepage loads with welcome message", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await expect(
      page.getByText("Welcome to Whale Agent")
    ).toBeVisible({ timeout: 30000 });
  });

  test("chat input is visible and accepts text", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    const input = page.locator("textarea, input[type='text']").first();
    await expect(input).toBeVisible({ timeout: 15000 });
    await input.fill("What is the collision risk near Monterey Bay?");
    await expect(input).toHaveValue(/collision risk/);
  });

  test("agent configs page loads", async ({ page }) => {
    await page.goto(`${BASE_URL}/#/agents`, { waitUntil: "networkidle" });
    // Should show at least some agent names
    await expect(
      page.getByText(/Whale|Route|Risk|Weather/i).first()
    ).toBeVisible({ timeout: 15000 });
  });

  test("gateway API config endpoint responds", async ({ request }) => {
    const response = await request.get(`${BASE_URL}/api/v1/config`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("webuiServerUrl");
  });

  test("send a test message and get orchestrator response", async ({
    page,
  }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Find the chat input
    const input = page.locator("textarea, input[type='text']").first();
    await expect(input).toBeVisible({ timeout: 15000 });

    // Type and send a message
    await input.fill("What whale species are most at risk near San Francisco?");
    await page.keyboard.press("Enter");

    // Wait for a response (agent text appearing in the chat)
    // The orchestrator should delegate to specialists and return within 60s
    await expect(
      page.locator('[class*="message"], [class*="bubble"], [class*="response"]')
        .filter({ hasText: /whale|species|risk|humpback|blue/i })
        .first()
    ).toBeVisible({ timeout: 120000 });
  });
});
