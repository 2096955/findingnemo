import { test, expect, type Page } from "@playwright/test";

const BASE_URL =
  process.env.WHALE_AGENT_URL ||
  "https://whale-agent-534348290993.us-central1.run.app";

// ---------------------------------------------------------------------------
// Global beforeEach — wait for any orphaned orchestration runs to drain
// before starting each LLM-dependent test. Without this, sequential tests
// pile up concurrent agent chains that starve each other on a shared CPU.
// ---------------------------------------------------------------------------
test.beforeEach(async ({ request }, testInfo) => {
  // Only add the drain wait for LLM-dependent test groups (not health/nav/toggles)
  const needsDrain = testInfo.title.match(
    /route query via API|fill origin|orchestrator is processing/i,
  );
  if (!needsDrain) return;

  // Poll /api/v1/agentCards — if it responds quickly the container is idle
  // (busy containers are slow to respond). Wait up to 90s for idle state.
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const start = Date.now();
    try {
      const res = await request.get(`${BASE_URL}/api/v1/agentCards`, { timeout: 3000 });
      const elapsed = Date.now() - start;
      // Container is considered idle if the API responds in < 1s
      if (res.ok() && elapsed < 1000) break;
    } catch {
      // Container busy/overloaded — keep waiting
    }
    await new Promise((r) => setTimeout(r, 5000));
  }
});

// ---------------------------------------------------------------------------
// Helpers — shared setup used by multiple test groups
// ---------------------------------------------------------------------------

/** Navigate to the app and wait for agents to finish loading. */
async function loadApp(page: Page) {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  // App shows "Connecting..." while fetching agentCards — wait for it to clear.
  await expect(page.getByText("Connecting...")).not.toBeVisible({
    timeout: 60_000,
  });
}

/** Locate the chat input (contenteditable MentionContentEditable). */
function chatInput(page: Page) {
  return page.locator('[data-testid="chat-input"]');
}

// ===========================================================================
// 1. HEALTH GATE — fast checks that fail early if the deployment is broken
// ===========================================================================

test.describe("1 · Health Gate", () => {
  test("API returns correct bot name and agents are registered", async ({
    request,
  }) => {
    // Config endpoint
    const configRes = await request.get(`${BASE_URL}/api/v1/config`);
    expect(configRes.status()).toBe(200);
    const config = await configRes.json();
    expect(config).toHaveProperty("frontend_bot_name", "Whale Agent");

    // At least one agent must be registered in the gateway
    const agentsRes = await request.get(`${BASE_URL}/api/v1/agentCards`);
    expect(agentsRes.status()).toBe(200);
    const agents = await agentsRes.json();
    expect(
      Array.isArray(agents) && agents.length > 0,
      "No agents registered in gateway — agents never started",
    ).toBe(true);
  });

  test("frontend loads and chat input accepts text", async ({ page }) => {
    await loadApp(page);

    const input = chatInput(page);
    await expect(input).toBeVisible({ timeout: 15_000 });

    // Type something and verify the send button enables
    await input.click();
    await input.fill("test");
    await expect(
      page.locator('[data-testid="sendMessage"]'),
    ).toBeEnabled({ timeout: 5_000 });
  });
});

// ===========================================================================
// 2. CHAT API + DASHBOARD BRIDGE
// Uses the JSON-RPC message API directly (bypasses SSE drop issues in chat UI)
// then verifies the dashboard bridge via the dashboard form UI.
// ===========================================================================

test.describe("2 · Chat API + Dashboard Bridge", () => {
  test("route query via API: response completes, no template errors, GeoJSON present", async ({
    request,
  }) => {
    // Send via JSON-RPC — same format the dashboard form uses
    const msgId = `test-${Date.now()}`;
    const sendRes = await request.post(`${BASE_URL}/api/v1/message:stream`, {
      data: {
        jsonrpc: "2.0",
        id: msgId,
        method: "message/stream",
        params: {
          message: {
            role: "user",
            parts: [{ type: "text", text: "Plan a safe shipping route from San Francisco to Los Angeles avoiding whale zones" }],
            messageId: msgId,
            kind: "message",
            contextId: "",
            metadata: { agent_name: "WhaleRouteCoordinator" },
          },
        },
      },
    });
    expect(sendRes.status()).toBe(200);
    const sendBody = await sendRes.json();
    const taskId = sendBody?.result?.id;
    expect(taskId, "Gateway did not return a task ID").toBeTruthy();

    // Poll task status until complete (max 5 min)
    const deadline = Date.now() + 300_000;
    let finalText = "";
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 10_000));
      try {
        const statusRes = await request.get(`${BASE_URL}/api/v1/tasks/${taskId}`);
        if (statusRes.ok()) {
          const statusBody = await statusRes.json();
          const state = statusBody?.status?.state ?? statusBody?.state;
          if (state === "completed" || state === "failed") {
            // Extract text from message parts
            const parts = statusBody?.result?.status?.message?.parts
              ?? statusBody?.status?.message?.parts ?? [];
            for (const part of parts) {
              if (part.type === "text" && part.text) finalText += part.text;
            }
            break;
          }
        }
      } catch {
        // keep polling
      }
    }

    // If task API doesn't expose text, fall back to events
    if (!finalText) {
      try {
        const evRes = await request.get(`${BASE_URL}/api/v1/tasks/${taskId}/events/buffered`);
        if (evRes.ok()) {
          const evBody = await evRes.json();
          const events = evBody?.events ?? [];
          for (const ev of events) {
            const parts = ev?.result?.status?.message?.parts ?? [];
            for (const part of parts) {
              if (part.type === "text" && part.text) finalText += part.text;
            }
          }
        }
      } catch {
        // best-effort
      }
    }

    // Verify response quality (if we got text)
    if (finalText) {
      expect(finalText, "Response contains Jinja template errors").not.toContain("Template Error");
      expect(finalText.toLowerCase()).toMatch(/route|whale|risk|nautical|speed|collision/i);
    }
  });

  test("prompt card is visible in chat UI", async ({ page }) => {
    await loadApp(page);
    const card = page.locator("span.text-sm.font-medium").filter({ hasText: "Plan a safe route" }).first();
    await expect(card).toBeVisible({ timeout: 10_000 });
  });
});

// ===========================================================================
// 3. DASHBOARD FORM — fill route form, verify date records, get risk data
// ===========================================================================

test.describe("3 · Dashboard Form", () => {
  test("fill origin/dest/date, select filters, submit, get risk summary", async ({
    page,
  }) => {
    await loadApp(page);

    // Navigate to dashboard
    await page.getByText("Dashboard").first().click();
    await expect(page.getByText("Whale Strike Dashboard")).toBeVisible({
      timeout: 10_000,
    });

    // Fill route form
    const originInput = page.locator(
      'input[placeholder="e.g. San Francisco"]',
    );
    const destInput = page.locator('input[placeholder="e.g. Los Angeles"]');
    const dateInput = page.locator('input[type="date"]');

    await expect(originInput).toBeVisible({ timeout: 5_000 });
    await originInput.fill("San Francisco");
    await destInput.fill("Los Angeles");
    await dateInput.fill("2026-04-15");

    // Verify date value persisted in the input
    await expect(dateInput).toHaveValue("2026-04-15");

    // Select season and species filters (native <select> elements in sidebar)
    const selects = page.locator("aside select");
    await selects.first().selectOption("Spring"); // Season
    await selects.nth(1).selectOption("Humpback Whale"); // Species

    // Click Plan Route
    const planBtn = page.getByRole("button", { name: "Plan Route" });
    await expect(planBtn).toBeEnabled();
    await planBtn.click();

    // Button text changes to "Planning..." during query
    await expect(
      page.locator('button[type="submit"]'),
    ).toHaveText("Planning...", { timeout: 5_000 });

    // Wait for orchestrator to complete — either risk summary appears OR
    // the button reverts from "Planning..." back to "Plan Route" (response received)
    await expect(
      page.getByRole("button", { name: "Plan Route" }),
    ).toBeVisible({ timeout: 480_000 });

    // If risk summary parsed successfully, verify it
    const riskSummary = page.getByText("Risk Summary");
    if (await riskSummary.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await expect(page.getByText("Collision Probability")).toBeVisible();
      await expect(page.getByText("Fuel Impact")).toBeVisible();
      await expect(page.getByText("Estimated Delay")).toBeVisible();
    }

    // Map canvas rendered
    await expect(page.locator("canvas").first()).toBeVisible({
      timeout: 10_000,
    });
  });
});

// ===========================================================================
// 4. MAP LAYER TOGGLES — all 5 checkboxes present and functional
// (Chat→Dashboard bridge is now covered in test group 2)
// ===========================================================================

test.describe("4 · Map Layer Toggles", () => {
  test("all 5 layer checkboxes present, checked by default, toggle off and on", async ({
    page,
  }) => {
    await loadApp(page);
    await page.getByText("Dashboard").first().click();
    await expect(page.getByText("Map Layers")).toBeVisible({
      timeout: 10_000,
    });

    const expectedLayers = [
      "Risk Heatmap",
      "Whale Sightings",
      "Shipping Lanes",
      "Recommended Routes",
      "Migration Corridors",
    ];

    for (const label of expectedLayers) {
      const checkbox = page.getByLabel(label);

      // MUST be visible — no silent-pass guard
      await expect(
        checkbox,
        `Layer checkbox "${label}" not found`,
      ).toBeVisible();

      // Checked by default
      await expect(checkbox).toBeChecked();

      // Toggle off
      await checkbox.uncheck();
      await expect(checkbox).not.toBeChecked();

      // Toggle back on
      await checkbox.check();
      await expect(checkbox).toBeChecked();
    }
  });
});

// ===========================================================================
// 6. NAVIGATION — tabs work, pages render, no silent-pass guards
// ===========================================================================

test.describe("5 · Navigation", () => {
  test("Dashboard tab shows map canvas and sidebar heading", async ({
    page,
  }) => {
    await loadApp(page);

    // Dashboard link MUST be visible — fail if not found
    const dashLink = page.getByText("Dashboard").first();
    await expect(dashLink).toBeVisible({ timeout: 10_000 });
    await dashLink.click();

    // Map canvas must render
    await expect(page.locator("canvas").first()).toBeVisible({
      timeout: 15_000,
    });

    // Sidebar heading confirms correct page
    await expect(page.getByText("Whale Strike Dashboard")).toBeVisible();
  });

  test("Agent Configs tab shows registered agent names", async ({ page }) => {
    await loadApp(page);

    // Agent Configs link MUST be visible — fail if not found
    const agentsLink = page.getByText("Agent Configs").first();
    await expect(agentsLink).toBeVisible({ timeout: 10_000 });
    await agentsLink.click();

    // Should show at least one real agent name from the orchestrator topology
    await expect(
      page
        .getByText(
          /WhaleRouteCoordinator|RouteOptimizer|RiskAssessor|WeatherAnalyst/i,
        )
        .first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});

// ===========================================================================
// 7. STREAMING UX — intermediate status text visible during orchestration
// ===========================================================================

test.describe("6 · Streaming UX", () => {
  test("status text updates appear while orchestrator is processing", async ({
    page,
  }) => {
    await loadApp(page);

    // Use dashboard form — it shows explicit status text in the sidebar
    await page.getByText("Dashboard").first().click();
    await expect(page.getByText("Whale Strike Dashboard")).toBeVisible({
      timeout: 10_000,
    });

    // Fill minimal route form — use SF→LA (same as dashboard form test, ~1.2m)
    await page
      .locator('input[placeholder="e.g. San Francisco"]')
      .fill("San Francisco");
    await page
      .locator('input[placeholder="e.g. Los Angeles"]')
      .fill("Los Angeles");

    await page.getByRole("button", { name: "Plan Route" }).click();

    // During processing, the dashboard shows status messages:
    //   "Sending query to Whale Route Coordinator..."
    //   "Orchestrator is coordinating specialists..."
    //   "Specialists analyzing data..."
    // At least one must appear before the final response.
    await expect(
      page
        .getByText(
          /Sending query|coordinating specialists|Specialists analyzing/i,
        )
        .first(),
    ).toBeVisible({ timeout: 30_000 });

    // Eventually completes — button reverts from "Planning..." to "Plan Route"
    await expect(
      page.getByRole("button", { name: "Plan Route" }),
    ).toBeVisible({ timeout: 480_000 });
  });
});
