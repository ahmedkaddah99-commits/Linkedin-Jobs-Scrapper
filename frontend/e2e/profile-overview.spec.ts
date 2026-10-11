import { expect, test } from 'playwright/test';
test('profile overview edits in a drawer and fills in a popup', async ({ page }, info) => {
  let settings = { account: {}, profile: { name: 'Alex Morgan', email: 'alex@example.com', role_title: 'Product Designer', location: 'Berlin', competencies: ['Research', 'Design'], education: [{ institution: 'Example University', degree_title: 'BSc', period: '2018-2022' }], recent_experience: [{ company: 'Example Studio', title: 'Designer', start_date: '2022-01', description: 'Designed useful products.', bullets: ['Built a useful product', 'Led research'] }] } };
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
  await drawer.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(drawer).toHaveCount(0);
  await expect(page.getByText('Senior Product Designer', { exact: true })).toBeVisible();
  await expect(page.getByText('Make your next move.')).toHaveCount(0);
  await expect(page.getByText('Your profile is private and secure.')).toHaveCount(0);
  await expect(page.getByRole('complementary', { name: 'Profile actions' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit skills', exact: true }).click();
  const skills = page.getByRole('dialog', { name: 'Edit profile section' });
  await skills.getByLabel('Skills', { exact: true }).fill('Power BI');
  await skills.getByLabel('Skills', { exact: true }).press('Enter');
  await skills.getByRole('button', { name: 'Remove Research', exact: true }).click();
  await skills.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(page.getByText('Power BI', { exact: true })).toBeVisible();
  expect(settings.profile.competencies).toEqual(['Design', 'Power BI']);
  await page.getByRole('button', { name: 'Edit education', exact: true }).click();
  const education = page.getByRole('dialog', { name: 'Edit profile section' });
  await expect(education.getByLabel('Degree', { exact: true })).toHaveValue('BSc');
  await education.getByLabel('Start date', { exact: true }).fill('2018-09');
  await education.getByLabel('End date', { exact: true }).fill('2022-06');
  await education.getByRole('button', { name: 'Update', exact: true }).click();
  expect(settings.profile.education[0].start_date).toBe('2018-09');
  await page.getByRole('button', { name: 'Edit work experience', exact: true }).click();
  const experience = page.getByRole('dialog', { name: 'Edit profile section' });
  await expect(experience.getByLabel('Bullet point 1', { exact: true })).toHaveValue('Built a useful product');
  await experience.getByLabel('Bullet point 1', { exact: true }).fill('Designed a successful product');
  await experience.getByRole('button', { name: 'Update', exact: true }).click();
  expect(settings.profile.recent_experience[0].bullets[0]).toBe('Designed a successful product');
  await page.getByRole('button', { name: 'Fill profile', exact: false }).click();
  await expect(page.getByRole('dialog', { name: 'Fill profile' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.reload();
  await expect(page.getByText('Senior Product Designer', { exact: true })).toBeVisible();
});

test('existing ready CV fills absent profile details and cleared skills stay cleared', async ({ page }) => {
  let settings = { profile: {}, profile_edited_fields: [], candidate_assets: [{ asset_kind: 'workspace_cv', display_name: 'existing-resume.pdf', metadata: { status: 'ready', parsed_profile: { name: 'CV Name', education: [{ institution: 'CV University', degree_title: 'MBA', period: '2020–2022' }], recent_experience: [{ title: 'Manager', company: 'CV Company', period: '2022–2025', bullets: ['Led a team'] }], competencies: ['SQL'] } } }] };
  await page.route('**/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/settings')) {
      if (route.request().method() === 'PUT') { const body = route.request().postDataJSON(); settings = { ...settings, profile: body.profile, profile_edited_fields: body.profile_edited_fields }; }
      return route.fulfill({ json: settings });
    }
    if (path.endsWith('/personalized-jobs/preferences')) return route.fulfill({ json: { preferences: {} } });
    return route.fulfill({ json: {} });
  });
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: 'CV Name' })).toBeVisible();
  await expect(page.getByText('MBA', { exact: true })).toBeVisible();
  await expect(page.getByText('Led a team', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit skills', exact: true }).click();
  await page.getByRole('button', { name: 'Remove SQL', exact: true }).click();
  await page.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.reload();
  await expect(page.getByText('SQL', { exact: true })).toHaveCount(0);
  await expect(page.getByText('MBA', { exact: true })).toBeVisible();
});

test('upload processing fills editable resume facts before saving', async ({ page }) => {
  let settings = { profile: {}, account: {} };
  await page.route('**/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/settings')) {
      if (route.request().method() === 'PUT') settings = { ...settings, profile: route.request().postDataJSON().profile };
      return route.fulfill({ json: settings });
    }
    if (path.endsWith('/documents/upload')) return route.fulfill({ json: { status_url: '/v1/cv-upload/test-upload', status: 'queued' } });
    if (path.endsWith('/cv-upload/test-upload')) return route.fulfill({ json: { status: 'ready', parsed: { name: 'Resume Name', competencies: ['SQL'], education: [{ institution: 'Resume University', degree_title: 'MSc' }], recent_experience: [{ title: 'Analyst', company: 'Resume Company', bullets: ['Analyzed outcomes'] }] } } });
    if (path.endsWith('/personalized-jobs/preferences')) return route.fulfill({ json: { preferences: {} } });
    return route.fulfill({ json: {} });
  });
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Edit personal details', exact: true }).click();
  await page.getByLabel('Upload resume', { exact: true }).setInputFiles({ name: 'resume.txt', mimeType: 'text/plain', buffer: Buffer.from('Resume facts') });
  await expect(page.getByLabel('Display name', { exact: true })).toHaveValue('Resume Name');
  await page.getByLabel('Display name', { exact: true }).fill('Reviewed Resume Name');
  await page.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Reviewed Resume Name' })).toBeVisible();
  await expect(page.getByText('MSc', { exact: true })).toBeVisible();
  await expect(page.getByText('Analyzed outcomes', { exact: true })).toBeVisible();
});
