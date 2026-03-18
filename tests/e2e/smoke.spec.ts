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
    // Use the nav tab button specifically — not sidebar "Chats" or "New Chat"
    await expect(
      page.getByRole("button", { name: "Chat", exact: true })
    ).toBeVisible({ timeout: 10000 });
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

test.describe("Dashboard — Route Rendering", () => {
  test("route query produces agent response and dashboard shows map data", async ({ page }) => {
    // Collect console errors for diagnostics
    const consoleErrors: string[] = [];
    const consoleLogs: string[] = [];
    page.on("console", msg => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
      else consoleLogs.push(msg.text());
    });

    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });

    // Step 1: Verify the agentCards API works from the browser context
    const agentCardsResponse = await page.evaluate(async () => {
      try {
        const res = await fetch("/api/v1/agentCards");
        const data = await res.json();
        return { status: res.status, count: Array.isArray(data) ? data.length : 0, names: Array.isArray(data) ? data.map((a: { name: string }) => a.name) : [] };
      } catch (e) {
        return { status: -1, count: 0, names: [], error: String(e) };
      }
    });
    console.log("agentCards API response:", JSON.stringify(agentCardsResponse));
    expect(agentCardsResponse.count, "No agents registered in gateway — agents never started").toBeGreaterThan(0);

    // Step 2: Wait for "Connecting..." to go away (app loaded agents)
    // If this fails, the React app didn't process the agent list
    await expect(page.getByText("Connecting...")).not.toBeVisible({ timeout: 60000 });

    // Step 3: Send a route query via the chat input
    const chatInput = page.locator('[data-testid="chat-input"]');
    await expect(chatInput).toBeVisible({ timeout: 10000 });
    await chatInput.click();
    await chatInput.fill("Plan a safe shipping route from San Francisco to Los Angeles avoiding whale zones");

    // Verify send button is enabled before clicking
    const sendBtn = page.locator('[data-testid="sendMessage"]');
    await expect(sendBtn).toBeEnabled({ timeout: 15000 });
    await sendBtn.click();

    // Step 4: Wait for a real agent response (not welcome text / example cards)
    // Agent responses appear in bubbles with class containing "mr-auto"
    // Wait up to 150s for cold-start + orchestration pipeline
    const agentResponse = page.locator('[class*="mr-auto"]')
      .filter({ hasText: /route|mile|nautical|risk|whale|francisco|angeles|waypoint|collision|coordinate/i })
      .first();
    await expect(agentResponse).toBeVisible({ timeout: 150000 });

    // Step 5: Navigate to dashboard and verify map data arrived
    await page.locator('button:has-text("Dashboard")').click();
    await page.waitForTimeout(3000);

    // Map canvas must exist
    const canvas = page.locator("canvas").first();
    await expect(canvas).toBeVisible({ timeout: 15000 });

    // "Showing data from chat query" banner means the GeoJSON bridge worked
    const chatDataBanner = page.getByText("Showing data from chat query");
    const bannerVisible = await chatDataBanner.isVisible().catch(() => false);

    if (!bannerVisible) {
      const bodyText = await page.locator("body").innerText();
      console.log(`Dashboard bridge: FeatureCollection=${bodyText.includes("FeatureCollection")}, render_type=${bodyText.includes("render_type")}`);
      console.log("Console errors:", consoleErrors.join(" | "));
      expect(bannerVisible, "Dashboard missing 'Showing data from chat query' — agent response lacks GeoJSON with render_type").toBe(true);
    }
  });
});

test.describe("Chat Output Quality", () => {
  test("species query returns aggregated summary, not raw occurrence list", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });

    const input = page.locator('[contenteditable="true"], textarea, input[type="text"]').first();
    await expect(input).toBeVisible({ timeout: 15000 });

    await input.fill("What whale species are most at risk in the North Pacific?");
    await page.keyboard.press("Enter");

    // Wait for response
    const responseArea = page.locator('[class*="message"], [class*="bubble"], [class*="response"]').last();
    await expect(responseArea).toBeVisible({ timeout: 120000 });
    await page.waitForTimeout(5000);

    const fullText = await page.locator("body").innerText();

    // Response should NOT be a raw dump of hundreds of identical scientific names
    const megapteraMatches = (fullText.match(/Megaptera novaeangliae/g) || []).length;
    const orcinusMatches = (fullText.match(/Orcinus orca/g) || []).length;
    expect(megapteraMatches).toBeLessThan(10);
    expect(orcinusMatches).toBeLessThan(10);

    // Should contain meaningful summary content
    expect(fullText.toLowerCase()).toMatch(/humpback|blue whale|fin whale|orca|right whale/i);
  });

  test("prompts page loads with seeded whale prompt templates", async ({ page }) => {
    // Verify seed ran by checking the API first
    const res = await page.request.get(`${BASE_URL}/api/v1/prompts/groups/all`);
    expect(res.status()).toBe(200);
    const groups = await res.json();
    const names = (Array.isArray(groups) ? groups : groups.groups ?? []).map((g: { name: string }) => g.name);
    expect(names.length).toBeGreaterThan(0);
    expect(names.some((n: string) => /route|risk|migration|species|whale/i.test(n))).toBe(true);

    // Also verify the page renders them
    await page.goto(`${BASE_URL}/#/prompts`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    await expect(
      page.getByText(/Route|Risk Assessment|Migration|Species/i).first()
    ).toBeVisible({ timeout: 15000 });
  });
});
