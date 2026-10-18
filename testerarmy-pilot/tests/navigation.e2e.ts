import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('landing loads without clipping the synthetic brand', async ({ app, screen, browser }) => {
  await app.open('/');
  await expect(screen.getByRole('heading', 'Synthetic Legal Portal')).toBeVisible();
  const bounds = await browser.evaluate(() => {
    const brand = document.querySelector('.brand');
    if (!brand) return null;
    const rect = brand.getBoundingClientRect();
    return {
      left: rect.left,
      right: rect.right,
      viewport: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    };
  });
  if (!bounds || bounds.left < -1 || bounds.right > bounds.viewport + 1 || bounds.scrollWidth > bounds.viewport + 1) {
    throw new Error('Brand is clipped or page overflows: ' + JSON.stringify(bounds));
  }
});

test('responsive navigation follows the About link', async ({ app, screen, browser }) => {
  await app.open('/');
  const mobile = await browser.evaluate(() => window.innerWidth <= 600);
  if (mobile) {
    await expect(screen.getByRole('navigation', 'Mobile navigation')).toBeHidden();
    await screen.getByText('Menu').tap();
    await expect(screen.getByRole('navigation', 'Mobile navigation')).toBeVisible();
  } else {
    await expect(screen.getByRole('navigation', 'Desktop navigation')).toBeVisible();
  }
  await screen.getByRole('link', 'About').tap();
  await expect(screen.getByRole('heading', 'About this demo')).toBeVisible();
});
