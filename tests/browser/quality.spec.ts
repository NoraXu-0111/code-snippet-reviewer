import { test, expect } from "@playwright/test";

test("human review completes with choices only and preserves drafts and export history", async ({
  page,
}, testInfo) => {
  await page.goto("/#/quality");
  await expect(page.getByLabel("Reviewer name")).toBeVisible();
  await page.screenshot({
    path: `work/quality-home-${testInfo.project.name}.png`,
  });
  await page.getByLabel("Reviewer name").fill(`Reviewer ${Date.now()}`);
  await page.getByRole("button", { name: "Start / resume review" }).click();
  await expect(
    page.getByRole("heading", { name: "Review with evidence" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "3. Assess the model outputs" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Reveal proposed reference" }),
  ).toBeDisabled();
  await page
    .getByRole("radio", { name: "I'm not sure yet", exact: true })
    .check();
  await page
    .getByRole("radio", {
      name: "Important requirements are missing",
      exact: true,
    })
    .check();
  // Switching cases retains an unsaved browser draft.
  await page.getByRole("button", { name: "2. mutable-default" }).click();
  await page.getByRole("button", { name: "1. empty-average" }).click();
  await expect(
    page.getByRole("radio", { name: "I'm not sure yet", exact: true }),
  ).toBeChecked();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("revision 1");
  await page.reload();
  await expect(
    page.getByRole("radio", {
      name: "Important requirements are missing",
      exact: true,
    }),
  ).toBeChecked();
  await expect(
    page.getByRole("heading", { name: "3. Assess the model outputs" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Reveal proposed reference" }).click();
  await page
    .getByRole("combobox", { name: "Reference verdict", exact: true })
    .selectOption("uncertain");
  await page
    .getByRole("radio", {
      name: "Need the intended inputs / behavior",
      exact: true,
    })
    .check();
  // Changing a verdict clears its selected reason instead of carrying an incompatible answer.
  await page
    .getByRole("combobox", { name: "Reference verdict", exact: true })
    .selectOption("needs_changes");
  await expect(
    page.getByRole("button", { name: "Reveal model outputs" }),
  ).toBeDisabled();
  await page
    .getByRole("radio", {
      name: "Lines, severity or explanation need correction",
      exact: true,
    })
    .check();
  await page.getByRole("button", { name: "Reveal model outputs" }).click();
  // Incomplete assessments cannot be silently marked complete.
  await page.getByRole("button", { name: "Complete & next case" }).click();
  await expect(page.getByRole("alert")).toContainText("Every finding needs");
  for (const run of await page.getByRole("region", { name: /^Run / }).all()) {
    await run
      .getByRole("combobox", { name: "Finding verdict", exact: true })
      .selectOption("uncertain");
    await run
      .getByRole("combobox", { name: "Line location", exact: true })
      .selectOption("good");
    await run
      .getByRole("combobox", { name: "Severity", exact: true })
      .selectOption("uncertain");
    await run
      .getByRole("combobox", { name: "Fix quality", exact: true })
      .selectOption("problem");
    await run
      .getByRole("radio", { name: "Need more context to judge", exact: true })
      .check();
    await run
      .getByRole("combobox", { name: "Coverage verdict", exact: true })
      .selectOption("uncertain");
  }
  await page.getByRole("button", { name: "Complete & next case" }).click();
  await expect(
    page.getByRole("heading", { name: "mutable-default", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("1/10 cases completed", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "1. empty-average" }).click();
  await expect(
    page.getByRole("combobox", { name: "Reference verdict", exact: true }),
  ).toHaveValue("needs_changes");
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Reference verdict", exact: true }),
  ).toHaveValue("needs_changes");
  const href = await page
    .getByRole("link", { name: "Export saved annotations" })
    .getAttribute("href");
  const response = await page.request.get(href!);
  const exported = await response.json();
  expect(exported.annotations["empty-average"].status).toBe("completed");
  expect(exported.annotations["empty-average"].referenceVerdict).toBe(
    "needs_changes",
  );
  expect(exported.annotations["empty-average"].referenceReason).toBe(
    "wrong_details",
  );
  expect(exported.annotations["empty-average"].proposedReference).toBe("");
  expect(exported.annotations["empty-average"].independentNotes).toBe("");
  expect(exported.annotations["empty-average"].contractNotes).toBe("");
  expect(exported.annotations["empty-average"].referenceNotes).toBe("");
  expect(
    exported.annotations["empty-average"].findings.every(
      (f: { notes: string; reason: string }) =>
        f.notes === "" && f.reason === "missing_context",
    ),
  ).toBeTruthy();
  expect(
    exported.annotations["empty-average"].coverage.every(
      (c: { notes: string }) => c.notes === "",
    ),
  ).toBeTruthy();
  expect(exported.history).toHaveLength(2);
  expect(exported.snapshot.originalReport.promptVersion).toBe("review-v2");
  // Partial draft writes through the API must restore omitted rows as pending in the UI.
  const sessionId = exported.sessionId;
  const draft = await page.request.put(
    `/api/quality/sessions/${sessionId}/cases/mutable-default`,
    {
      data: {
        revision: 0,
        independentNotes: "The default list is shared between calls.",
        contractNotes: "Intent to accumulate across calls is not specified.",
        referenceVerdict: "uncertain",
        referenceNotes: "Verify the intended lifetime of the list.",
      },
    },
  );
  expect(draft.ok()).toBeTruthy();
  await page.goto(`/#/quality/${sessionId}?case=mutable-default`);
  await page.reload();
  await page.getByRole("button", { name: "Reveal model outputs" }).click();
  await expect(
    page.getByRole("combobox", { name: "Finding verdict", exact: true }),
  ).toHaveCount(2);
  await expect(
    page
      .getByRole("combobox", { name: "Finding verdict", exact: true })
      .first(),
  ).toHaveValue("pending");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("revision 2");
  await page
    .getByRole("heading", { name: "3. Assess the model outputs" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `work/quality-assessment-${testInfo.project.name}.png`,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("concurrent tabs cannot overwrite a newer human judgment", async ({
  page,
  context,
}) => {
  await page.goto("/#/quality");
  await page.getByLabel("Reviewer name").fill(`Conflict ${Date.now()}`);
  await page.getByRole("button", { name: "Start / resume review" }).click();
  await expect(
    page.getByRole("heading", { name: "Review with evidence" }),
  ).toBeVisible();
  const other = await context.newPage();
  await other.goto(page.url());
  await other.getByText("Optional code notes", { exact: true }).click();
  await page.getByText("Optional code notes", { exact: true }).click();
  await expect(
    other.getByLabel("Your observations and evidence"),
  ).toBeVisible();
  await page
    .getByLabel("Your observations and evidence")
    .fill("First reviewer tab saved this evidence.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("revision 1");
  await other
    .getByLabel("Your observations and evidence")
    .fill("Stale tab text must be retained but not overwrite saved evidence.");
  await other.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(other.getByRole("alert")).toContainText("saved in another tab");
  await expect(
    other.getByLabel("Your observations and evidence"),
  ).toContainText("Stale tab text");
  await page.reload();
  await expect(page.getByLabel("Your observations and evidence")).toContainText(
    "First reviewer tab",
  );
  await other.close();
});
