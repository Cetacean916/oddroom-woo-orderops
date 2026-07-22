import fs from 'node:fs';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const baseUrl = (process.env.PF07_BASE_URL || '').replace(/\/$/, '');
if (!/^https?:\/\//.test(baseUrl)) {
  throw new Error('PF07_BASE_URL must identify the staging storefront.');
}
const adminBaseUrl = (process.env.PF07_ADMIN_BASE_URL || '').replace(/\/$/, '');

const viewports = [390, 768, 1440];
const routes = [
  ['home', '/'],
  ['shop', '/shop/'],
  ['category', '/product-category/demo-products/'],
  ['product', '/product/offset-dock/'],
  ['cart', '/cart/'],
  ['checkout', '/checkout/'],
  ['account', '/my-account/'],
  ['tracking', '/order-tracking/'],
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
  const context = await browser.newContext({
    viewport: { width, height: 1000 },
    extraHTTPHeaders: { 'ngrok-skip-browser-warning': 'pf07-validation' },
  });
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
      await page.goto(`${baseUrl}/product/offset-dock/`, { waitUntil: 'domcontentloaded' });
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
      const root = document.documentElement;
      const previousScrollBehavior = root.style.scrollBehavior;
      root.style.scrollBehavior = 'auto';
      const maximumScroll = Math.max(0, root.scrollHeight - window.innerHeight);
      for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
        window.scrollTo(0, Math.round(maximumScroll * fraction));
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      await Promise.all([...document.images].map((image) => {
        if (image.complete) return Promise.resolve();
        return new Promise((resolve) => {
          const finish = () => resolve();
          image.addEventListener('load', finish, { once: true });
          image.addEventListener('error', finish, { once: true });
          setTimeout(finish, 5000);
        });
      }));
      window.scrollTo(0, 0);
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      root.style.scrollBehavior = previousScrollBehavior;
    });
    await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
    const metrics = await page.evaluate(() => {
      const root = document.documentElement;
      const clipsOverflow = (value) => ['auto', 'clip', 'hidden', 'scroll'].includes(value);
      const effectiveBox = (element) => {
        const box = element.getBoundingClientRect();
        const visibleBox = {
          left: box.left,
          right: box.right,
          top: box.top,
          bottom: box.bottom,
        };
        for (let ancestor = element.parentElement;
          ancestor && ancestor !== document.documentElement;
          ancestor = ancestor.parentElement) {
          const style = getComputedStyle(ancestor);
          const ancestorBox = ancestor.getBoundingClientRect();
          if (clipsOverflow(style.overflowX)) {
            visibleBox.left = Math.max(visibleBox.left, ancestorBox.left);
            visibleBox.right = Math.min(visibleBox.right, ancestorBox.right);
          }
          if (clipsOverflow(style.overflowY)) {
            visibleBox.top = Math.max(visibleBox.top, ancestorBox.top);
            visibleBox.bottom = Math.min(visibleBox.bottom, ancestorBox.bottom);
          }
        }
        return {
          ...visibleBox,
          width: Math.max(0, visibleBox.right - visibleBox.left),
          height: Math.max(0, visibleBox.bottom - visibleBox.top),
        };
      };
      const visible = (element) => {
        const style = getComputedStyle(element);
        const box = effectiveBox(element);
        const closedDetails = element.closest('details:not([open])');
        return style.display !== 'none'
          && style.visibility !== 'hidden'
          && Number.parseFloat(style.opacity || '1') > 0
          && box.width > 0
          && box.height > 0
          && !closedDetails
          && !element.matches('.oddroom-skip:not(:focus)')
          && !element.closest('[aria-hidden="true"],[hidden],[inert]');
      };
      const images = [...document.images].map((image) => ({
        complete: image.complete,
        natural_width: image.naturalWidth,
        alt_present: image.hasAttribute('alt'),
        placeholder_marker: /placeholder/i.test(`${image.currentSrc} ${image.alt}`),
      }));
      const controls = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button]')]
        .filter(visible);
      const clipped = controls.filter((element) => {
        const box = effectiveBox(element);
        return box.width > 0 && (box.left < -1 || box.right > root.clientWidth + 1);
      }).length;
      let overlappingControls = 0;
      for (let leftIndex = 0; leftIndex < controls.length; leftIndex += 1) {
        for (let rightIndex = leftIndex + 1; rightIndex < controls.length; rightIndex += 1) {
          const left = controls[leftIndex];
          const right = controls[rightIndex];
          if (left.contains(right) || right.contains(left)) continue;
          const sameComposite = ['.woocommerce-product-gallery', '.password-input']
            .some((selector) => left.closest(selector) && left.closest(selector) === right.closest(selector));
          if (sameComposite) continue;
          const leftBox = effectiveBox(left);
          const rightBox = effectiveBox(right);
          const overlapWidth = Math.min(leftBox.right, rightBox.right) - Math.max(leftBox.left, rightBox.left);
          const overlapHeight = Math.min(leftBox.bottom, rightBox.bottom) - Math.max(leftBox.top, rightBox.top);
          if (overlapWidth > 2 && overlapHeight > 2) overlappingControls += 1;
        }
      }
      const accessibleName = (element) => {
        const id = element.getAttribute('id');
        const explicitLabel = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
        const labelledBy = (element.getAttribute('aria-labelledby') || '')
          .split(/\s+/)
          .filter(Boolean)
          .map((labelId) => document.getElementById(labelId)?.innerText || '')
          .join(' ');
        return [
          element.getAttribute('aria-label'),
          element.getAttribute('title'),
          element.getAttribute('alt'),
          labelledBy,
          explicitLabel?.innerText,
          element.closest('label')?.innerText,
          element.querySelector('img[alt]')?.getAttribute('alt'),
          element.innerText,
          element.value && ['button', 'submit'].includes(element.type) ? element.value : '',
        ].some((value) => typeof value === 'string' && value.trim() !== '');
      };
      const unlabeledControls = controls.filter((element) => !accessibleName(element)).length;
      const keyboardInoperableControls = controls.filter((element) => {
        const native = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName);
        return !native && element.getAttribute('role') === 'button' && element.tabIndex < 0;
      }).length;
      const bodyText = document.body.innerText;
      const internalCopyPattern = /lorem ipsum|\bTODO\b|Product proof surface|Synthetic catalog|Cart rehearsal|No-funds checkout|Synthetic order account|Store fixtures are being prepared|\bUncategorized\b/i;
      return {
        client_width: root.clientWidth,
        scroll_width: root.scrollWidth,
        body_scroll_width: document.body.scrollWidth,
        page_overflow_px: Math.max(root.scrollWidth, document.body.scrollWidth) - root.clientWidth,
        document_language: document.documentElement.lang,
        korean_locale: /^ko(?:-|_)/i.test(document.documentElement.lang),
        image_count: images.length,
        broken_image_count: images.filter((image) => !image.complete || image.natural_width < 1).length,
        image_without_alt_count: images.filter((image) => !image.alt_present).length,
        placeholder_asset_count: images.filter((image) => image.placeholder_marker).length,
        visible_control_count: controls.length,
        horizontally_clipped_control_count: clipped,
        overlapping_control_count: overlappingControls,
        unlabeled_control_count: unlabeledControls,
        keyboard_inoperable_control_count: keyboardInoperableControls,
        unresolved_skeleton_count: document.querySelectorAll('.wc-block-components-skeleton__element,.wc-block-components-skeleton--checkout-payment').length,
        visible_h1_count: [...document.querySelectorAll('h1')].filter((heading) => {
          const style = getComputedStyle(heading);
          const box = heading.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
        }).length,
        required_font_load_failures: [
          document.fonts?.check('16px "Offset Grotesk"') === false,
          document.fonts?.check('32px "Offset Editorial"') === false,
        ].filter(Boolean).length,
        forbidden_copy: internalCopyPattern.test(bodyText),
      };
    });
    const axe = await new AxeBuilder({ page }).analyze();
    const moderateOrWorse = axe.violations
      .filter((violation) => ['critical', 'serious', 'moderate'].includes(violation.impact))
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
      moderate_or_worse: moderateOrWorse,
      critical_or_serious: moderateOrWorse.filter((violation) => ['critical', 'serious'].includes(violation.impact)),
      console_errors: [...new Set(consoleErrors)],
      failed_resources: failedResources,
    };
    evidence.storefront.push(observation);
    if (observation.http_status !== 200
      || !observation.expected_path_reached
      || observation.page_overflow_px > 1
      || observation.broken_image_count > 0
      || observation.placeholder_asset_count > 0
      || observation.horizontally_clipped_control_count > 0
      || observation.overlapping_control_count > 0
      || observation.unlabeled_control_count > 0
      || observation.keyboard_inoperable_control_count > 0
      || observation.unresolved_skeleton_count > 0
      || observation.required_font_load_failures > 0
      || observation.visible_h1_count !== 1
      || !observation.korean_locale
      || observation.forbidden_copy
      || observation.moderate_or_worse.length > 0
      || observation.console_errors.length > 0
      || observation.failed_resources.length > 0) {
      evidence.failures.push({ surface: name, viewport_width: width });
    }
  }
  await context.close();
}

const adminUser = process.env.PF07_ADMIN_USER || '';
const passwordFile = process.env.PF07_ADMIN_PASSWORD_FILE || '';
if ([adminUser, passwordFile, adminBaseUrl].some(Boolean)
  && ![adminUser, passwordFile, adminBaseUrl].every(Boolean)) {
  throw new Error('PF07_ADMIN_BASE_URL, PF07_ADMIN_USER, and PF07_ADMIN_PASSWORD_FILE must be supplied together.');
}
if (adminBaseUrl && !/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::[1-9][0-9]{0,4})?$/.test(adminBaseUrl)) {
  throw new Error('PF07_ADMIN_BASE_URL must identify a loopback-only HTTP origin.');
}
if (adminUser && passwordFile) {
  const password = fs.readFileSync(passwordFile, 'utf8').trim();
  for (const width of viewports) {
    const context = await browser.newContext({
      viewport: { width, height: 1000 },
      extraHTTPHeaders: { 'X-OddRoom-Private-Admin': 'loopback' },
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const consoleErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    await page.goto(`${adminBaseUrl}/wp-login.php`, { waitUntil: 'domcontentloaded' });
    await page.fill('#user_login', adminUser);
    await page.fill('#user_pass', password);
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      page.click('#wp-submit'),
    ]);
    const response = await page.goto(`${adminBaseUrl}/wp-admin/admin.php?page=oddroom-orderops`, { waitUntil: 'networkidle' });
    await page.locator('.oddroom-orderops').waitFor();
    await page.evaluate(async () => { if (document.fonts) await document.fonts.ready; });
    const metrics = await page.evaluate(() => {
      const root = document.querySelector('.oddroom-orderops');
      const scroller = root.querySelector('.oddroom-table-wrap');
      const eventList = root.querySelector('.oddroom-event-list');
      const dataSurface = scroller || eventList;
      const buttons = [...root.querySelectorAll('button,input[type=submit],a.button')].filter((button) => {
        const style = getComputedStyle(button);
        const box = button.getBoundingClientRect();
        return style.display !== 'none'
          && style.visibility !== 'hidden'
          && box.width > 0
          && box.height > 0
          && !button.closest('details:not([open])')
          && !button.closest('[aria-hidden="true"],[hidden],[inert]');
      });
      let overlappingActions = 0;
      for (let leftIndex = 0; leftIndex < buttons.length; leftIndex += 1) {
        for (let rightIndex = leftIndex + 1; rightIndex < buttons.length; rightIndex += 1) {
          const left = buttons[leftIndex];
          const right = buttons[rightIndex];
          if (left.contains(right) || right.contains(left)) continue;
          const leftBox = left.getBoundingClientRect();
          const rightBox = right.getBoundingClientRect();
          const overlapWidth = Math.min(leftBox.right, rightBox.right) - Math.max(leftBox.left, rightBox.left);
          const overlapHeight = Math.min(leftBox.bottom, rightBox.bottom) - Math.max(leftBox.top, rightBox.top);
          if (overlapWidth > 2 && overlapHeight > 2) overlappingActions += 1;
        }
      }
      const unlabeledActions = buttons.filter((button) => ![
        button.getAttribute('aria-label'), button.getAttribute('title'), button.innerText, button.value,
      ].some((value) => typeof value === 'string' && value.trim() !== '')).length;
      const documentOverflowContained = document.documentElement.scrollWidth
        <= document.documentElement.clientWidth + 1;
      const dataSurfaceOverflowContained = scroller
        ? scroller.scrollWidth > scroller.clientWidth && documentOverflowContained
        : Boolean(eventList)
          && eventList.scrollWidth <= eventList.clientWidth + 1
          && documentOverflowContained;
      return {
        root_selector: '.oddroom-orderops',
        document_client_width: document.documentElement.clientWidth,
        document_scroll_width: document.documentElement.scrollWidth,
        root_width: Math.round(root.getBoundingClientRect().width),
        data_surface_mode: scroller ? 'table_scroller' : 'event_card_list',
        table_scroller_client_width: dataSurface?.clientWidth ?? 0,
        table_scroller_scroll_width: dataSurface?.scrollWidth ?? 0,
        table_overflow_contained: dataSurfaceOverflowContained,
        protected_action_count: buttons.length,
        overlapping_protected_action_count: overlappingActions,
        unlabeled_protected_action_count: unlabeledActions,
        horizontally_clipped_action_count: buttons.filter((button) => {
          const box = button.getBoundingClientRect();
          const ownerScroller = button.closest('.oddroom-table-wrap');
          return !ownerScroller && box.width > 0
            && (box.left < -1 || box.right > document.documentElement.clientWidth + 1);
        }).length,
      };
    });
    const axe = await new AxeBuilder({ page }).include('.oddroom-orderops').analyze();
    const moderateOrWorse = axe.violations
      .filter((violation) => ['critical', 'serious', 'moderate'].includes(violation.impact))
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
      moderate_or_worse: moderateOrWorse,
      critical_or_serious: moderateOrWorse.filter((violation) => ['critical', 'serious'].includes(violation.impact)),
      console_errors: [...new Set(consoleErrors)],
    };
    evidence.admin.push(observation);
    if (observation.http_status !== 200
      || !observation.table_overflow_contained
      || observation.horizontally_clipped_action_count > 0
      || observation.overlapping_protected_action_count > 0
      || observation.unlabeled_protected_action_count > 0
      || observation.moderate_or_worse.length > 0
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
