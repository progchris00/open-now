import { expect, test } from "@playwright/test";


for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "desktop", width: 1440, height: 900 },
]) {
  test(`home page loads at ${viewport.width} px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: "OpenNow system health" }),
    ).toBeVisible();
    await expect(page.getByText("Database", { exact: true })).toBeVisible();
  });
}
