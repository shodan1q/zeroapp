/**
 * Actually run a generated web app before it ships.
 *
 * Static checks prove a file parses. They cannot tell you that `APP.boot()`
 * threw on line one and the user is looking at a blank screen -- and that
 * failure is invisible to the rest of the pipeline, because hvigor packages a
 * broken page just as happily as a working one.
 *
 * This harness loads index.html in jsdom, executes every script in document
 * order, boots the app, then pokes at it: switches tabs, types in the search
 * box, opens a detail row. Everything it learns is reported as structured JSON
 * so the Python side can feed real stack traces back to the model.
 *
 * Scripts are executed one at a time rather than by letting jsdom fetch them,
 * so a failure is attributed to the file that caused it.
 *
 * Usage: node verify.mjs <job.json>   where job.json is {dir, contract}
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const MAX_MESSAGE = 600;
const SETTLE_MS = 60;

function truncate(text, limit = MAX_MESSAGE) {
  const value = String(text ?? "");
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
}

function describeError(error) {
  if (!error) return { message: "unknown error" };
  const stack = typeof error.stack === "string" ? error.stack.split("\n").slice(0, 4).join("\n") : "";
  return { message: truncate(error.message ?? error), stack: truncate(stack) };
}

/** Script srcs in document order, so execution matches what the browser does. */
function scriptOrder(html) {
  const order = [];
  const re = /<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi;
  let match;
  while ((match = re.exec(html)) !== null) order.push(match[1]);
  return order;
}

async function settle(window, ms = SETTLE_MS) {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function main() {
  const jobPath = process.argv[2];
  if (!jobPath) {
    console.log(JSON.stringify({ ok: false, fatal: "no job file given" }));
    return;
  }
  const job = JSON.parse(readFileSync(jobPath, "utf8"));
  const dir = job.dir;
  const contract = job.contract || {};

  let JSDOM;
  let VirtualConsole;
  try {
    ({ JSDOM, VirtualConsole } = await import("jsdom"));
  } catch {
    console.log(JSON.stringify({ ok: true, skipped: "jsdom is not installed" }));
    return;
  }

  const html = readFileSync(join(dir, "index.html"), "utf8");
  const errors = [];
  const consoleErrors = [];

  // VirtualConsole is an EventEmitter; the older sendTo() adapter was removed
  // in jsdom 30.
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("error", (...args) => consoleErrors.push(truncate(args.join(" "))));
  virtualConsole.on("jsdomError", (error) => errors.push({ stage: "page", ...describeError(error) }));

  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url: "https://zerodev.local/",
    virtualConsole,
  });
  const { window } = dom;
  installBrowserShims(window);

  // Measure whether the app boots itself, rather than inferring it from whether
  // the DOM ended up populated. The inference broke on apps whose only mounts
  // are legitimately empty until the user acts. Intercepting the assignment to
  // window.APP lets us wrap boot() before anything can call it.
  let appValue;
  let bootCalled = false;
  Object.defineProperty(window, "APP", {
    configurable: true,
    get: () => appValue,
    set: (value) => {
      appValue = value;
      if (value && typeof value.boot === "function") {
        const original = value.boot;
        value.boot = function wrappedBoot(...args) {
          bootCalled = true;
          return original.apply(this, args);
        };
      }
    },
  });

  window.addEventListener("error", (event) => {
    errors.push({ stage: "runtime", ...describeError(event.error || { message: event.message }) });
  });
  window.addEventListener("unhandledrejection", (event) => {
    errors.push({ stage: "promise", ...describeError(event.reason) });
  });

  // -- execute every script, attributing failures to their file ------------
  for (const src of scriptOrder(html)) {
    let code;
    try {
      code = readFileSync(join(dir, src), "utf8");
    } catch (error) {
      errors.push({ stage: src, message: `could not read ${src}: ${truncate(error.message)}` });
      continue;
    }
    try {
      window.eval(code);
    } catch (error) {
      errors.push({ stage: src, ...describeError(error) });
    }
  }

  // Apps commonly boot on DOMContentLoaded; fire the lifecycle either way.
  try {
    window.document.dispatchEvent(new window.Event("DOMContentLoaded", { bubbles: true }));
    window.dispatchEvent(new window.Event("load"));
  } catch (error) {
    errors.push({ stage: "lifecycle", ...describeError(error) });
  }
  await settle(window);

  const app = window.APP;
  const checks = {
    app_global: Boolean(app),
    views_registered: app && app.views ? Object.keys(app.views).length : 0,
    features_registered: app && app.features ? Object.keys(app.features).length : 0,
    charts_registered: app && app.charts ? Object.keys(app.charts).length : 0,
    data_collections: window.APP_DATA
      ? Object.entries(window.APP_DATA)
          .filter(([, v]) => Array.isArray(v))
          .map(([k, v]) => ({ name: k, records: v.length }))
      : [],
  };

  // If nothing booted itself, boot explicitly so a missing call is reported as
  // its own defect rather than showing up as "every mount is empty".
  const selfBooted = bootCalled || countPopulated(window, contract) > 0;
  let booted = false;
  if (!selfBooted && app && typeof app.boot === "function") {
    try {
      app.boot();
      booted = true;
      await settle(window);
    } catch (error) {
      errors.push({ stage: "APP.boot()", ...describeError(error) });
    }
  }
  checks.self_booted = selfBooted;
  checks.boot_forced = booted;

  // -- mount points --------------------------------------------------------
  // Every declared mount must EXIST; only the ones backed by a non-empty
  // collection must be POPULATED. Flagging a search-results container for being
  // empty before anyone searched would be a false positive.
  const mounts = {};
  const emptyMounts = [];
  const missingMounts = [];
  const mustFill = new Set(dataBackedMounts(contract, window));
  for (const id of mountIds(contract)) {
    const node = window.document.getElementById(id);
    if (!node) {
      missingMounts.push(id);
      continue;
    }
    const children = node.children.length;
    const text = (node.textContent || "").trim().length;
    mounts[id] = { children, text, expected: mustFill.has(id) };
    if (mustFill.has(id) && children === 0 && text === 0) emptyMounts.push(id);
  }
  checks.mounts = mounts;

  // -- interaction probes --------------------------------------------------
  const interactions = [];

  for (const tab of [...window.document.querySelectorAll("[data-view], .tab, nav button")].slice(0, 8)) {
    const label = tab.getAttribute("data-view") || tab.getAttribute("aria-label") || tab.textContent.trim().slice(0, 12);
    const before = errors.length;
    try {
      tab.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
      await settle(window, 20);
    } catch (error) {
      errors.push({ stage: `tab:${label}`, ...describeError(error) });
    }
    interactions.push({ name: `tab:${label}`, ok: errors.length === before });
  }

  const search = window.document.querySelector("input[type=search], input[type=text], input:not([type])");
  if (search) {
    const before = errors.length;
    try {
      search.value = "a";
      search.dispatchEvent(new window.Event("input", { bubbles: true }));
      search.dispatchEvent(new window.Event("change", { bubbles: true }));
      await settle(window, 20);
    } catch (error) {
      errors.push({ stage: "search", ...describeError(error) });
    }
    interactions.push({ name: "search", ok: errors.length === before });
  }

  const row = window.document.querySelector("[data-id]");
  if (row) {
    const before = errors.length;
    try {
      row.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
      await settle(window, 20);
    } catch (error) {
      errors.push({ stage: "detail", ...describeError(error) });
    }
    interactions.push({ name: "detail", ok: errors.length === before });
  }
  checks.interactions = interactions;

  const report = {
    ok:
      errors.length === 0 &&
      Boolean(checks.app_global) &&
      // The harness booting on the app's behalf hides a page that would
      // never render on a device.
      !checks.boot_forced &&
      missingMounts.length === 0 &&
      emptyMounts.length === 0,
    errors,
    console_errors: consoleErrors.slice(0, 10),
    missing_mounts: missingMounts,
    empty_mounts: emptyMounts,
    checks,
  };
  console.log(JSON.stringify(report));

  // jsdom keeps the event loop alive: pretendToBeVisual runs a rAF loop, and
  // any setInterval the app started still holds a handle. Without an explicit
  // teardown the process hangs after printing a perfectly good report, which
  // the Python side can only interpret as "the app never finished booting".
  try {
    window.close();
  } catch {
    /* closing is best-effort; the exit below is what actually matters */
  }
  process.exit(0);
}

/**
 * Fill in the browser APIs jsdom leaves unimplemented.
 *
 * Without these, jsdom raises "Not implemented: Window's scrollTo()" and the
 * report blames the app for using an ordinary browser API. A gate that invents
 * defects is worse than no gate -- it sends the rework loop chasing bugs that
 * do not exist. These are all no-ops or trivial stubs: the app is being checked
 * for whether it runs, not for what it paints.
 */
function installBrowserShims(window) {
  const noop = () => {};
  window.scrollTo = noop;
  window.scrollBy = noop;
  window.Element.prototype.scrollTo = noop;
  window.Element.prototype.scrollIntoView = noop;

  if (!window.matchMedia) {
    window.matchMedia = (query) => ({
      matches: false,
      media: query,
      addEventListener: noop,
      removeEventListener: noop,
      addListener: noop,
      removeListener: noop,
      onchange: null,
      dispatchEvent: () => false,
    });
  }

  for (const name of ["IntersectionObserver", "ResizeObserver", "MutationObserver"]) {
    if (!window[name]) {
      window[name] = class {
        observe() {}
        unobserve() {}
        disconnect() {}
        takeRecords() {
          return [];
        }
      };
    }
  }

  // Charts frequently measure their container before drawing; zeros would make
  // them bail out early and report an empty mount that a real device fills.
  const rect = window.Element.prototype.getBoundingClientRect;
  window.Element.prototype.getBoundingClientRect = function getRect() {
    const base = rect ? rect.call(this) : {};
    return { ...base, x: 0, y: 0, top: 0, left: 0, width: 390, height: 640, right: 390, bottom: 640 };
  };
  Object.defineProperty(window.HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 390 });
  Object.defineProperty(window.HTMLElement.prototype, "offsetHeight", { configurable: true, get: () => 640 });
}

/** Mounts that are expected to hold content: the ones bound to a collection. */
function dataBackedMounts(contract, window) {
  const ids = [];
  for (const view of contract.views || []) {
    for (const section of view.sections || []) {
      if (!section || !section.mount_id) continue;
      const collection = section.collection;
      // A mount with no collection behind it -- a search results list, an empty
      // state, a detail sheet -- is legitimately empty until the user acts.
      if (!collection) continue;
      const records = window.APP_DATA && window.APP_DATA[collection];
      if (Array.isArray(records) && records.length > 0) ids.push(section.mount_id);
    }
  }
  return ids;
}

function mountIds(contract) {
  const ids = new Set();
  for (const view of contract.views || []) {
    for (const section of view.sections || []) {
      if (section && section.mount_id) ids.add(section.mount_id);
    }
  }
  return [...ids];
}

function countPopulated(window, contract) {
  let count = 0;
  // Only mounts that should hold data count as evidence of a boot; a
  // legitimately-empty search container must not read as 'never started'.
  const expected = dataBackedMounts(contract, window);
  for (const id of (expected.length ? expected : mountIds(contract))) {
    const node = window.document.getElementById(id);
    if (node && (node.children.length > 0 || (node.textContent || "").trim())) count += 1;
  }
  return count;
}

main().catch((error) => {
  console.log(JSON.stringify({ ok: false, fatal: truncate(error && error.stack ? error.stack : error) }));
});
