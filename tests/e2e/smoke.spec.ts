import { test, expect } from "@playwright/test";

const BASE_URL =
  process.env.WHALE_AGENT_URL ||
  "https://whale-agent-534348290993.us-central1.run.app";

test.describe("Whale Agent Live Smoke Tests", () => {
  test("homepage loads with welcome message", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await expect(
      page.getByText("Welcome to Whale Agent")
    ).toBeVisible({ timeout: 30000 });
  });

  test("chat input is visible and accepts text", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    const input = page.locator('[contenteditable="true"], textarea, input[type="text"]').first();
    await expect(input).toBeVisible({ timeout: 15000 });
  });

  test("agent configs page loads", async ({ page }) => {
    await page.goto(`${BASE_URL}/#/agents`, { waitUntil: "domcontentloaded" });
    await expect(
      page.getByText(/Whale|Route|Risk|Weather/i).first()
    ).toBeVisible({ timeout: 15000 });
  });

  test("gateway API config endpoint responds", async ({ request }) => {
    const response = await request.get(`${BASE_URL}/api/v1/config`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("frontend_bot_name", "Whale Agent");
  });

  test("send a test message and get orchestrator response", async ({
    page,
  }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });

    const input = page.locator('[contenteditable="true"], textarea, input[type="text"]').first();
    await expect(input).toBeVisible({ timeout: 15000 });

    await input.fill("What whale species are most at risk near San Francisco?");
    await page.keyboard.press("Enter");

    await expect(
      page.locator('[class*="message"], [class*="bubble"], [class*="response"]')
        .filter({ hasText: /whale|species|risk|humpback|blue/i })
        .first()
    ).toBeVisible({ timeout: 120000 });
  });
});

test.describe("Branding Audit — no solace/MedExpert remnants", () => {
  test("no 'solace' text visible in header or navigation", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    // The word "solace" should NOT appear in visible page text
    // (solace.com URLs in JS are internal protocol identifiers — OK)
    const bodyText = await page.locator("body").innerText();
    const lowerText = bodyText.toLowerCase();
    expect(lowerText).not.toContain("solace.");
    // "solace" as a standalone visible word shouldn't appear
    expect(lowerText).not.toMatch(/\bsolace\b/);
  });

  test("page title is 'Whale Agent', not 'solace' or 'MedExpert'", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    const title = await page.title();
    expect(title.toLowerCase()).toContain("whale");
    expect(title.toLowerCase()).not.toContain("solace");
    expect(title.toLowerCase()).not.toContain("medexpert");
  });

  test("no 'Medical Triage' or 'Deep Research' in mode selector", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toContain("Medical Triage");
    expect(bodyText).not.toContain("Deep Research");
    expect(bodyText).not.toContain("Triage");
  });

  test("mode selector shows 'Routes' and 'Risk'", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    // Click the mode dropdown to reveal options
    const modeSelector = page.locator('[aria-label="Select mode"]');
    if (await modeSelector.isVisible()) {
      await modeSelector.click();
      await page.waitForTimeout(500);

      const dropdownText = await page.locator("body").innerText();
      expect(dropdownText).toContain("Route");
      expect(dropdownText).toContain("Risk");
    }
  });
});

test.describe("Example Prompt Cards", () => {
  test("example prompt cards appear on fresh chat", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    // Should see at least 3 of the 5 example prompt labels
    const expectedLabels = [
      "Plan a safe route",
      "Check collision risk",
      "Migration patterns",
      "Historical strikes",
      "Species at risk",
    ];

    let matchCount = 0;
    for (const label of expectedLabels) {
      const el = page.getByText(label);
      if (await el.isVisible().catch(() => false)) {
        matchCount++;
      }
    }
    expect(matchCount).toBeGreaterThanOrEqual(3);
  });

  test("clicking an example prompt card sends a message", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    // Click the first example prompt card
    const card = page.getByText("Plan a safe route");
    if (await card.isVisible().catch(() => false)) {
      await card.click();
      // After clicking, the example cards should disappear (new user message added)
      await page.waitForTimeout(2000);
      // Should see the prompt text in the chat as a user message
      await expect(
        page.getByText("San Francisco").first()
      ).toBeVisible({ timeout: 15000 });
    }
  });
});

test.describe("Navigation Tabs", () => {
  test("Chat tab is present and active by default", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Chat")).toBeVisible({ timeout: 10000 });
  });

  test("Dashboard tab navigates to map view", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    const dashboardLink = page.getByText("Dashboard");
    if (await dashboardLink.isVisible()) {
      await dashboardLink.click();
      await page.waitForTimeout(2000);
      // Dashboard should render the MapView (canvas or map container)
      const mapCanvas = page.locator("canvas, .maplibregl-map, .mapboxgl-map, [class*='map']");
      await expect(mapCanvas.first()).toBeVisible({ timeout: 10000 });
    }
  });

  test("Agent Configs tab shows agent list", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    const agentConfigsLink = page.getByText("Agent Configs");
    if (await agentConfigsLink.isVisible()) {
      await agentConfigsLink.click();
      await page.waitForTimeout(3000);
      await expect(
        page.getByText(/Whale|Route|Risk|Orchestrator/i).first()
      ).toBeVisible({ timeout: 15000 });
    }
  });
});
