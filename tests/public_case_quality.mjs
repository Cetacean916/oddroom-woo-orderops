import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const caseUrl = process.env.PF07_PUBLIC_CASE_URL || "https://cetacean916.github.io/portfolio-showcase/case.html?id=pf07";
const browser = await chromium.launch({ channel: "chrome", headless: true });
const observations = [];

try {
  for (const width of [390, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    await page.goto(caseUrl, { waitUntil: "networkidle", timeout: 30000 });
    await page.locator("[data-case-root] .case-page").waitFor({ state: "visible" });
    const audit = await page.evaluate(() => {
      const visibleActions = [...document.querySelectorAll("a,button")].filter((node) => {
        const style = getComputedStyle(node); const rect = node.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
      });
      return {
        title: document.title,
        h1: document.querySelector("h1")?.textContent?.trim() || "",
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        brokenImages: [...document.images].filter((image) => image.complete && image.naturalWidth === 0).length,
        clippedActions: visibleActions.filter((node) => node.scrollWidth > node.clientWidth + 2 || node.scrollHeight > node.clientHeight + 2).length,
        scoreRows: document.querySelectorAll("[data-proof-scorecard] tbody tr").length,
        evidenceLinks: document.querySelectorAll("[data-evidence-links] a").length,
        boundaryText: document.querySelector("[data-claims-boundary]")?.textContent || "",
        availability: document.querySelector("[data-hosting-availability]")?.textContent || "",
        videos: document.querySelectorAll("video").length,
      };
    });
    const axe = await new AxeBuilder({ page }).analyze();
    const seriousOrCritical = axe.violations.filter((item) => ["serious", "critical"].includes(item.impact)).length;
    if (!audit.title.includes("OddRoom") || !audit.h1.includes("OrderOps")) throw new Error(`${width}: title or heading missing`);
    if (audit.scrollWidth > audit.viewportWidth + 1 || audit.brokenImages || audit.clippedActions) throw new Error(`${width}: layout or asset failure ${JSON.stringify(audit)}`);
    if (audit.scoreRows < 7 || audit.evidenceLinks < 4 || audit.videos < 2) throw new Error(`${width}: proof/video sections incomplete ${JSON.stringify(audit)}`);
    for (const phrase of ["exactly-once", "실결제", "Slack", "ON_DEMAND_ONLY"]) {
      if (!(audit.boundaryText + audit.availability).includes(phrase)) throw new Error(`${width}: missing boundary ${phrase}`);
    }
    if (seriousOrCritical || consoleErrors.length) {
      const seriousViolations = axe.violations
        .filter((item) => ["serious", "critical"].includes(item.impact))
        .map((item) => ({ id: item.id, impact: item.impact, targets: item.nodes.map((node) => node.target) }));
      throw new Error(`${width}: accessibility/console failure ${JSON.stringify({ seriousOrCritical, seriousViolations, consoleErrors })}`);
    }
    observations.push({ width, serious_or_critical: seriousOrCritical, page_overflow: false, clipped_actions: 0, broken_images: 0, console_errors: 0 });
    await context.close();
  }
  console.log(JSON.stringify({ schema_version: 1, result: "PASS", case_url: caseUrl, observations }));
} finally {
  await browser.close();
}
