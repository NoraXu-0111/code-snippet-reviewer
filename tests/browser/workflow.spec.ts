import { test, expect, type Page } from "@playwright/test";

async function create(page: Page, code?: string) {
  await page.goto("/#/new");
  if (code) {
    await page
      .getByRole("textbox", { name: "Title", exact: true })
      .fill("Browser test");
    await page.getByRole("textbox", { name: "Code", exact: true }).fill(code);
  } else {
    await page.getByLabel("Start with an example").selectOption("average");
  }
  await page.getByRole("button", { name: "Save snippet", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Source code" }),
  ).toBeVisible();
}
async function review(page: Page) {
  await page
    .getByRole("button", { name: "Review snippet", exact: true })
    .click();
  await expect(
    page.getByText("Empty input causes division by zero.", { exact: true }),
  ).toBeVisible();
}
async function discuss(page: Page) {
  await page
    .getByRole("button", { name: "Discuss with AI", exact: true })
    .click();
  await expect(
    page.getByLabel("Ask a follow-up", { exact: true }),
  ).toBeEnabled();
}

test("create, review, resolve, converse, rerun, restore historical conversation", async ({
  page,
}) => {
  await create(page);
  await review(page);
  await page.getByRole("button", { name: "Show line 2 in code" }).click();
  await expect(page.getByText("Lines 2–2 selected")).toBeVisible();
  await page.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(page.getByText("Accepted", { exact: true })).toBeVisible();
  await discuss(page);
  await page
    .getByLabel("Ask a follow-up", { exact: true })
    .fill("Give an example");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByText("Answer with 0 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".chat-assistant script")).toHaveCount(0);
  await page
    .getByLabel("Ask a follow-up", { exact: true })
    .fill("Explain that");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByText("Answer with 1 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  const history = page.getByLabel("Review history", { exact: true });
  const oldId = await history.locator("option").nth(1).getAttribute("value");
  await page.getByRole("button", { name: "Run new review" }).click();
  await expect(page.getByText("Open", { exact: true })).toBeVisible();
  await expect(history.locator("option")).toHaveCount(3);
  await discuss(page);
  await expect(
    page.getByText(
      "Need an example, or think this is a false positive? Ask here.",
    ),
  ).toBeVisible();
  await history.selectOption(oldId!);
  await expect(
    page.getByText("Viewing an earlier review. Code is unchanged."),
  ).toBeVisible();
  await expect(page.getByText("Accepted", { exact: true })).toBeVisible();
  await page.reload();
  await expect(history).toHaveValue(oldId!);
  await discuss(page);
  await expect(
    page.getByText("Answer with 1 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close discussion" }).click();
  await expect(
    page.getByRole("button", { name: "Discuss with AI" }),
  ).toBeFocused();
});

test("provider failures retry without duplicate question; drafts survive closing", async ({
  page,
}) => {
  await create(page, "# FAIL_ONCE\nresult = 1 / 0");
  await page
    .getByRole("button", { name: "Review snippet", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review failed", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry review", exact: true }).click();
  await expect(
    page.getByText("Empty input causes division by zero.", { exact: true }),
  ).toBeVisible();
  await discuss(page);
  await page.getByLabel("Ask a follow-up", { exact: true }).fill("fail once");
  await page.getByRole("button", { name: "Close discussion" }).click();
  await discuss(page);
  await expect(page.getByLabel("Ask a follow-up", { exact: true })).toHaveValue(
    "fail once",
  );
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByText("Simulated reply failure. Please retry."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry reply", exact: true }).click();
  await expect(
    page.getByText("Answer with 0 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".chat-user")).toHaveCount(1);
});

test("lost submission response survives reload and recovers one persisted turn", async ({
  page,
}) => {
  await create(page);
  await review(page);
  await discuss(page);
  let lost = false,
    recovered = false;
  await page.route("**/api/findings/*/discussion", async (route) => {
    if (route.request().method() === "POST" && !lost) {
      await route.fetch();
      lost = true;
      await route.abort();
    } else if (route.request().method() === "GET" && lost && !recovered) {
      await route.abort();
    } else {
      if (route.request().method() === "POST") recovered = true;
      await route.continue();
    }
  });
  await page.getByLabel("Ask a follow-up", { exact: true }).fill("Recover me");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByRole("button", { name: "Check submission" }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Discuss with AI" }).click();
  await page.getByRole("button", { name: "Check submission" }).click();
  await expect(
    page.getByText("Answer with 0 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".chat-user")).toHaveCount(1);
});

test("zero findings and dashboard filtering", async ({ page }) => {
  await create(page, "def add(a, b):\n    return a + b");
  await page
    .getByRole("button", { name: "Review snippet", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "No issues found" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "← All snippets" }).click();
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("python");
  await page
    .getByRole("combobox", { name: "Review status", exact: true })
    .selectOption("reviewed");
  await expect(
    page.getByRole("cell", { name: "Not reviewed", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Browser test", exact: true }).last(),
  ).toBeVisible();
});

test("sample form protects drafts, wide conversation fits viewport and keyboard focus", async ({
  page,
}) => {
  await page.goto("/#/new");
  await page
    .getByRole("textbox", { name: "Title", exact: true })
    .fill("My draft");
  await expect(page.getByLabel("Start with an example")).toBeDisabled();
  await page.getByRole("textbox", { name: "Title", exact: true }).fill("");
  await page.getByLabel("Start with an example").selectOption("async");
  await expect(
    page.getByRole("textbox", { name: "Code", exact: true }),
  ).toHaveValue(/items.forEach/);
  await page.getByRole("button", { name: "Save snippet" }).click();
  await review(page);
  await discuss(page);
  await expect(
    page.getByRole("region", { name: "Discussion workspace" }),
  ).toBeFocused();
  const fits = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  );
  expect(fits).toBe(true);
  await page.getByRole("button", { name: "Close discussion" }).click();
  await expect(
    page.getByRole("button", { name: "Discuss with AI" }),
  ).toBeFocused();
});

test("same finding supports independent conversations, drafts and reload selection", async ({
  page,
}) => {
  await create(page);
  await review(page);
  await discuss(page);
  const composer = page.getByLabel("Ask a follow-up", { exact: true });
  await composer.fill("Original question");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByText("Answer with 0 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  const selector = page.getByRole("combobox", {
    name: "Conversation",
    exact: true,
  });
  const original = await selector.inputValue();
  await composer.fill("Unsent original draft");
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await expect(selector.locator("option")).toHaveCount(2);
  const second = await selector.inputValue();
  expect(second).not.toBe(original);
  await expect(page.locator(".chat-user")).toHaveCount(0);
  await expect(composer).toHaveValue("");
  await composer.fill("Fresh question");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByText("Answer with 0 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  await composer.fill("Follow up fresh");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByText("Answer with 1 earlier exchanges.", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await discuss(page);
  await expect(selector).toHaveValue(second);
  await expect(page.locator(".chat-user")).toHaveCount(2);
  await composer.fill("Unsent second draft");
  await selector.selectOption(original);
  await expect(page.locator(".chat-user")).toHaveCount(1);
  await expect(composer).toHaveValue("Unsent original draft");
  await selector.selectOption(second);
  await expect(composer).toHaveValue("Unsent second draft");
  await page.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(page.locator(".chat-user")).toHaveCount(2);
});

test("lost new conversation response recovers one conversation after reload", async ({
  page,
}) => {
  await create(page);
  await review(page);
  await discuss(page);
  let lost = false;
  await page.route("**/api/findings/*/conversations", async (route) => {
    if (!lost && route.request().method() === "POST") {
      await route.fetch();
      lost = true;
      await route.abort();
    } else await route.continue();
  });
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Check new conversation" }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Discuss with AI" }).click();
  await page.getByRole("button", { name: "Check new conversation" }).click();
  const selector = page.getByRole("combobox", {
    name: "Conversation",
    exact: true,
  });
  await expect(selector.locator("option")).toHaveCount(2);
  await expect(page.locator(".chat-user")).toHaveCount(0);
  await expect(
    page.getByLabel("Ask a follow-up", { exact: true }),
  ).toBeEnabled();
});

for (const reload of [false, true]) {
  test(`lost review submission recovers once ${reload ? "after reload" : "without reload"}`, async ({
    page,
  }) => {
    await create(page);
    const snippetId = page.url().split("/snippets/")[1]!.split("?")[0];
    const url = `/api/snippets/${snippetId}/reviews`;
    const identities: string[] = [];
    let drop = true;
    await page.route(`**${url}`, async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      identities.push(route.request().postDataJSON().clientRequestId);
      const response = await route.fetch();
      expect(response.ok()).toBeTruthy();
      if (drop) {
        drop = false;
        await route.abort("failed");
      } else await route.fulfill({ response });
    });
    await page
      .getByRole("button", { name: "Review snippet", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Check submission", exact: true }),
    ).toBeEnabled();
    await expect
      .poll(async () => {
        const history = await (await page.request.get(url)).json();
        return history.reviews[0]?.status;
      })
      .toBe("succeeded");
    if (reload) await page.reload();
    await page
      .getByRole("button", { name: "Check submission", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Run new review", exact: true }),
    ).toBeEnabled();
    await expect(
      page.getByText("Empty input causes division by zero.", { exact: true }),
    ).toBeVisible();
    expect(identities).toHaveLength(2);
    expect(identities[1]).toBe(identities[0]);
    expect((await (await page.request.get(url)).json()).reviews).toHaveLength(
      1,
    );
    expect(
      (
        await (
          await page.request.get(`/test/reviewer-calls/${snippetId}`)
        ).json()
      ).calls,
    ).toBe(1);
    // An explicit new review now uses a fresh identity and invokes the provider once more.
    await page
      .getByRole("button", { name: "Run new review", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (
            await (
              await page.request.get(`/test/reviewer-calls/${snippetId}`)
            ).json()
          ).calls,
      )
      .toBe(2);
    expect(identities).toHaveLength(3);
    expect(identities[2]).not.toBe(identities[0]);
    expect((await (await page.request.get(url)).json()).reviews).toHaveLength(
      2,
    );
  });
}
