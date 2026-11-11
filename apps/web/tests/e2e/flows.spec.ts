import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const email = () => `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@x.io`;

async function signUpOnboarded(page: Page) {
  const r = await page.request.post("/api/auth/signup", { data: { email: email(), password: "pw-123456", persona: "ayesha_ml" } });
  expect(r.ok()).toBeTruthy();
  const me = await r.json();
  await page.request.put("/api/auth/settings", { data: { ...me.settings, onboarded: true, marketplace: "gigsim", floor: 30 } });
}

async function draftFor(req: APIRequestContext, job: string): Promise<string> {
  const run = await (await req.post(`/api/jobs/${job}/analyse`)).json();
  await expect.poll(async () => (await (await req.get(`/api/runs/${run.id}`)).json()).status, { timeout: 60_000 }).toBe("awaiting_approval");
  return run.id;
}

async function statusOf(req: APIRequestContext, id: string) {
  return (await (await req.get(`/api/runs/${id}`)).json()).status;
}

test("onboarding: sign up, pick persona, connect GigSim, set rates, land in inbox", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /create an account/i }).click();
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("pw-123456");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Set up GigBid" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByTestId("connect-gigsim").click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Floor rate (USD/h) never bid below").fill("30");
  await page.getByTestId("finish-onboarding").click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  await expect(page.getByTestId("inbox-row").first()).toBeVisible({ timeout: 60_000 });
});

test("approving a proposal submits it exactly once", async ({ page }) => {
  await signUpOnboarded(page);
  const id = await draftFor(page.request, "a01");
  await page.goto(`/studio/${id}`);
  await expect(page.getByTestId("dry-run")).toContainText("Connects");
  await expect(page.getByTestId("claim").first()).toBeVisible();
  await page.getByTestId("approve").click();
  await expect.poll(() => statusOf(page.request, id), { timeout: 60_000 }).toBe("submitted");
  const again = await page.request.post(`/api/approvals/${id}`, { data: { action: "approve" } });
  expect(again.status()).toBe(409);
  await page.goto("/pipeline");
  await expect(page.getByTestId("card-submitted")).toHaveCount(1);
});

test("rejecting needs a reason and never sends", async ({ page }) => {
  await signUpOnboarded(page);
  const id = await draftFor(page.request, "a02");
  await page.goto(`/studio/${id}`);
  await expect(page.getByTestId("reject")).toBeDisabled();
  await page.getByLabel("Reject with a reason").fill("Budget too low for this scope");
  await page.getByTestId("reject").click();
  await expect.poll(() => statusOf(page.request, id), { timeout: 60_000 }).toBe("rejected");
  await page.reload();
  await expect(page.getByText("Budget too low for this scope")).toBeVisible();
});

test("editing a draft shows a diff and re-checks compliance before sending", async ({ page }) => {
  await signUpOnboarded(page);
  const id = await draftFor(page.request, "a03");
  await page.goto(`/studio/${id}`);
  const editor = page.getByTestId("draft-editor");
  await expect(editor).not.toHaveValue("");   // the studio fills the editor after it loads the pending draft
  const before = await editor.inputValue();
  await editor.fill(before.split(". ").slice(1).join(". ") + " Contact me at me@example.com.");
  await expect(page.getByTestId("edit-diff")).toBeVisible();
  await page.reload();   // a refresh never loses the pending approval
  await expect(page.getByTestId("draft-editor")).toHaveValue(before);
  await page.getByTestId("draft-editor").fill(before.split(". ").slice(1).join(". ") + " Contact me at me@example.com.");
  await page.getByTestId("approve-edit").click();
  // compliance strips the contact detail from the edit, so the user must approve the cleaned text before anything is sent
  await expect.poll(async () => {
    const ev = await (await page.request.get(`/api/runs/${id}/events`)).json();
    return ev.filter((e: any) => e.data.node === "compliance").length;
  }, { timeout: 60_000 }).toBe(2);   // once for the draft, again for the user's edit
  await expect.poll(() => statusOf(page.request, id), { timeout: 60_000 }).toBe("awaiting_approval");
  const pending = await (await page.request.get(`/api/proposals/${id}`)).json();
  expect(pending.payload.draft.cover_letter).not.toContain("me@example.com");
  expect(pending.payload.compliance.violations).toContain("contact details removed");
  expect((await page.request.post(`/api/approvals/${id}`, { data: { action: "approve" } })).ok()).toBeTruthy();
  await expect.poll(() => statusOf(page.request, id), { timeout: 60_000 }).toBe("submitted");
});

test("degraded mode: marketplace down shows a banner", async ({ page }) => {
  await signUpOnboarded(page);
  await page.route("**/api/health", (r) => r.fulfill({ json: { api: "ok", marketplace: "down", marketplace_adapter: "gigsim", model_profile: "offline", detail: "MarketplaceDown" } }));
  await page.goto("/inbox");
  await expect(page.getByTestId("degraded-banner")).toContainText("Marketplace unavailable");
});
