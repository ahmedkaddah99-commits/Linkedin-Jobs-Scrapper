import { expect, test } from 'playwright/test';
test('profile overview edits in a drawer and fills in a popup', async ({ page }, info) => {
  let settings = { account: {}, profile: { name: 'Alex Morgan', email: 'alex@example.com', role_title: 'Product Designer', location: 'Berlin', competencies: ['Research', 'Design'], education: [{ institution: 'Example University', degree: 'BSc' }], recent_experience: [{ company: 'Example Studio', title: 'Designer', start_date: '2022-01', description: 'Designed useful products.' }] } };
  const preferences = { target_roles: ['Designer'], preferred_locations: ['Berlin'] };
  await page.route('**/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/settings')) { if (route.request().method() === 'PUT') settings = { ...settings, ...route.request().postDataJSON() }; return route.fulfill({ json: settings }); }
    if (path.endsWith('/personalized-jobs/preferences')) return route.fulfill({ json: { preferences } });
    return route.fulfill({ json: {} });
  });
  await page.goto('/jobs');
  await page.getByRole('link', { name: 'View and edit full profile' }).click();
  await expect(page.getByRole('heading', { name: 'Alex Morgan' })).toBeVisible();
  await page.screenshot({ path: info.outputPath('overview.png'), fullPage: true });
  await page.getByRole('button', { name: 'Edit personal details' }).click();
  const drawer = page.getByRole('dialog', { name: 'Edit profile section' });
  await drawer.getByLabel('Role title', { exact: true }).fill('Senior Product Designer');
  await page.screenshot({ path: info.outputPath('editor.png') });
  await drawer.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(drawer).toHaveCount(0);
  await expect(page.getByText('Senior Product Designer', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Fill profile', exact: false }).click();
  await expect(page.getByRole('dialog', { name: 'Fill profile' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.reload();
  await expect(page.getByText('Senior Product Designer', { exact: true })).toBeVisible();
});
