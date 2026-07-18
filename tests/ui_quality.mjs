import fs from 'node:fs';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const baseUrl = (process.env.PF07_BASE_URL || '').replace(/\/$/, '');
if (!/^https?:\/\//.test(baseUrl)) {
  throw new Error('PF07_BASE_URL must identify the staging storefront.');
}

const viewports = [390, 768, 1440];
const routes = [
  ['home', '/'],
  ['shop', '/shop/'],
  ['product', '/product/oddroom-drop-kit/'],
  ['cart', '/cart/'],
  ['checkout', '/checkout/'],
  ['account', '/my-account/'],
];
const evidence = {
  schema_version: 1,
  toolchain: { playwright: '1.61.1', axe_core: '4.12.1' },
  observed_at_utc: new Date().toISOString(),
  base_url_alias: 'PF07_STAGING',
  storefront: [],
  admin: [],
  failures: [],
};

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PF07_CHROME_PATH || '/usr/bin/google-chrome',
});
evidence.toolchain.chrome = browser.version();

for (const width of viewports) {
  const context = await browser.newContext({ viewport: { width, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  let consoleErrors = [];
  let failedResources = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('response', (response) => {
    if (response.status() >= 400
      && ['document', 'image', 'stylesheet', 'script', 'font'].includes(response.request().resourceType())) {
      failedResources.push({ status: response.status(), resource_type: response.request().resourceType() });
    }
  });

  for (const [name, route] of routes) {
    if (name === 'cart') {
      await page.goto(`${baseUrl}/product/oddroom-drop-kit/`, { waitUntil: 'domcontentloaded' });
      const add = page.locator('button.single_add_to_cart_button');
      await add.waitFor({ state: 'visible' });
      await add.click();
      await page.waitForLoadState('domcontentloaded');
    }
    consoleErrors = [];
    failedResources = [];
    const response = await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });
    if (['cart', 'checkout'].includes(name)) {
      await page.waitForFunction(
        () => !document.querySelector('.wc-block-components-skeleton__element,.wc-block-components-skeleton--checkout-payment'),
        null,
        { timeout: 15000 },
      ).catch(() => {});
    }
    await page.evaluate(async () => {
      window.scrollTo(0, document.documentElement.scrollHeight);
      await new Promise((resolve) => setTimeout(resolve, 350));
      window.scrollTo(0, 0);
    });
    await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
    const metrics = await page.evaluate(() => {
      const root = document.documentElement;
      const images = [...document.images].map((image) => ({
        complete: image.complete,
        natural_width: image.naturalWidth,
        alt_present: image.hasAttribute('alt'),
      }));
      const controls = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button]')]
        .filter((element) => {
          const style = getComputedStyle(element);
          return style.display !== 'none'
            && style.visibility !== 'hidden'
            && !element.closest('[aria-hidden="true"],[hidden],[inert]');
        });
      const clipped = controls.filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && (box.left < -1 || box.right > root.clientWidth + 1);
      }).length;
      return {
        client_width: root.clientWidth,
        scroll_width: root.scrollWidth,
        body_scroll_width: document.body.scrollWidth,
        page_overflow_px: Math.max(root.scrollWidth, document.body.scrollWidth) - root.clientWidth,
        image_count: images.length,
        broken_image_count: images.filter((image) => !image.complete || image.natural_width < 1).length,
        image_without_alt_count: images.filter((image) => !image.alt_present).length,
        visible_control_count: controls.length,
        horizontally_clipped_control_count: clipped,
        forbidden_copy: /lorem ipsum|\bTODO\b/i.test(document.body.innerText),
      };
    });
    const axe = await new AxeBuilder({ page }).analyze();
    const severe = axe.violations
      .filter((violation) => ['critical', 'serious'].includes(violation.impact))
      .map((violation) => ({
        rule_id: violation.id,
        impact: violation.impact,
        targets: violation.nodes.map((node) => node.target.join(' ')),
      }));
    const expectedPath = new URL(`${baseUrl}${route}`).pathname.replace(/\/$/, '') || '/';
    const actualPath = new URL(page.url()).pathname.replace(/\/$/, '') || '/';
    const observation = {
      page: name,
      viewport_width: width,
      url_alias: `PF07_${name.toUpperCase()}`,
      mode: 'full_document',
      http_status: response?.status() ?? null,
      expected_path_reached: actualPath === expectedPath,
      ...metrics,
      critical_or_serious: severe,
      console_errors: [...new Set(consoleErrors)],
      failed_resources: failedResources,
    };
    evidence.storefront.push(observation);
    if (observation.http_status !== 200
      || !observation.expected_path_reached
      || observation.page_overflow_px > 1
      || observation.broken_image_count > 0
      || observation.horizontally_clipped_control_count > 0
      || observation.forbidden_copy
      || observation.critical_or_serious.length > 0
      || observation.console_errors.length > 0
      || observation.failed_resources.length > 0) {
      evidence.failures.push({ surface: name, viewport_width: width });
    }
  }
  await context.close();
}

const adminUser = process.env.PF07_ADMIN_USER || '';
const passwordFile = process.env.PF07_ADMIN_PASSWORD_FILE || '';
if (adminUser && passwordFile) {
  const password = fs.readFileSync(passwordFile, 'utf8').trim();
  for (const width of viewports) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const consoleErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    await page.goto(`${baseUrl}/wp-login.php`, { waitUntil: 'domcontentloaded' });
    await page.fill('#user_login', adminUser);
    await page.fill('#user_pass', password);
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      page.click('#wp-submit'),
    ]);
    const response = await page.goto(`${baseUrl}/wp-admin/admin.php?page=oddroom-orderops`, { waitUntil: 'networkidle' });
    await page.locator('.oddroom-orderops').waitFor();
    await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
    const metrics = await page.evaluate(() => {
      const root = document.querySelector('.oddroom-orderops');
      const scroller = root.querySelector('.oddroom-table-wrap');
      const buttons = [...root.querySelectorAll('button,input[type=submit],a.button')];
      return {
        root_selector: '.oddroom-orderops',
        document_client_width: document.documentElement.clientWidth,
        document_scroll_width: document.documentElement.scrollWidth,
        root_width: Math.round(root.getBoundingClientRect().width),
        table_scroller_client_width: scroller.clientWidth,
        table_scroller_scroll_width: scroller.scrollWidth,
        table_overflow_contained: scroller.scrollWidth > scroller.clientWidth
          && document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        protected_action_count: buttons.length,
        horizontally_clipped_action_count: buttons.filter((button) => {
          const box = button.getBoundingClientRect();
          const ownerScroller = button.closest('.oddroom-table-wrap');
          return !ownerScroller && box.width > 0
            && (box.left < -1 || box.right > document.documentElement.clientWidth + 1);
        }).length,
      };
    });
    const axe = await new AxeBuilder({ page }).include('.oddroom-orderops').analyze();
    const severe = axe.violations
      .filter((violation) => ['critical', 'serious'].includes(violation.impact))
      .map((violation) => ({
        rule_id: violation.id,
        impact: violation.impact,
        targets: violation.nodes.map((node) => node.target.join(' ')),
      }));
    const observation = {
      page: 'admin',
      viewport_width: width,
      url_alias: 'PF07_ADMIN',
      mode: 'scoped',
      http_status: response?.status() ?? null,
      ...metrics,
      critical_or_serious: severe,
      console_errors: [...new Set(consoleErrors)],
    };
    evidence.admin.push(observation);
    if (observation.http_status !== 200
      || !observation.table_overflow_contained
      || observation.horizontally_clipped_action_count > 0
      || observation.critical_or_serious.length > 0
      || observation.console_errors.length > 0) {
      evidence.failures.push({ surface: 'admin', viewport_width: width });
    }
    await context.close();
  }
}

await browser.close();
const output = JSON.stringify(evidence, null, 2) + '\n';
if (process.env.PF07_UI_EVIDENCE) {
  fs.writeFileSync(process.env.PF07_UI_EVIDENCE, output, { mode: 0o600 });
}
process.stdout.write(JSON.stringify({
  status: evidence.failures.length === 0 ? 'PASS' : 'FAIL',
  storefront_observations: evidence.storefront.length,
  admin_observations: evidence.admin.length,
  failures: evidence.failures,
}) + '\n');
if (evidence.failures.length > 0) process.exitCode = 1;
