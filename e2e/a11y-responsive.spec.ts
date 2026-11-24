import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";


for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
]) {
  test(`delivery details is accessible and responsive at ${viewport.width} px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/delivery-details");

    await expect(
      page.getByRole("heading", { name: "Where should we deliver?" }),
    ).toBeVisible();
    const map = page.getByTestId("map-shell");
    const form = page.getByRole("form", { name: "Delivery address" });
    await expect(map).toBeVisible();
    await expect(form).toBeVisible();

    const mapBox = await map.boundingBox();
    const formBox = await form.boundingBox();
    expect(mapBox).not.toBeNull();
    expect(formBox).not.toBeNull();
    if (!mapBox || !formBox) return;

    if (viewport.width < 768) {
      expect(Math.round(mapBox.height)).toBe(180);
      expect(formBox.y).toBeGreaterThan(mapBox.y + mapBox.height);
    } else {
      expect(Math.abs(mapBox.y - formBox.y)).toBeLessThan(8);
      expect(mapBox.x).toBeGreaterThan(formBox.x + formBox.width - 8);
      expect(mapBox.width).toBeGreaterThan(viewport.width >= 1280 ? 560 : 300);
    }

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
}
