// A small harness: open the analyser's page in jsdom against a running server, drive it, and collect errors.
import { JSDOM, VirtualConsole } from "jsdom";

export async function openPage(base) {
  const errors = [];
  // jsdom doesn't emulate the browser's "unhandledrejection" event; the analyser marks errors it has already shown as `handled`
  process.on("unhandledRejection", reason => { if (!(reason && reason.handled)) errors.push("unhandled rejection: " + (reason && reason.stack || reason)); });
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", e => errors.push("script error: " + (e.detail && e.detail.stack || e.message)));
  virtualConsole.on("error", (...a) => errors.push("console.error: " + a.map(String).join(" ")));
  const dom = await JSDOM.fromURL(base + "/", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole,
    beforeParse(w) {
      w.fetch = (url, opts) => fetch(new URL(url, base), opts);        // jsdom has no fetch; use node's, against the server
      w.Element.prototype.scrollIntoView = function () {};
      w.scrollTo = () => {};
      w.confirm = () => true;
      w.URL.createObjectURL = () => "blob:test";
      w.URL.revokeObjectURL = () => {};
    },
  });
  const w = dom.window;
  await waitFor(() => w.document.readyState === "complete", "page load");
  const page = {
    dom, window: w, errors, base,
    $: s => w.document.querySelector(s),
    $$: s => [...w.document.querySelectorAll(s)],
    eval: code => w.eval(code),
    /** Wait until #main has stopped loading and stopped changing. */
    async settle(what = "page", ms = 20000) {
      const t0 = Date.now();
      let last = "", stable = 0;
      await sleep(60);
      while (Date.now() - t0 < ms) {
        const main = w.document.querySelector("#main");
        const loading = main && main.querySelector(".loading");
        const sig = main ? main.innerHTML.length + ":" + main.querySelectorAll("*").length : "";
        stable = !loading && sig === last ? stable + 1 : 0;
        last = sig;
        if (stable >= 4) return;
        await sleep(60);
      }
      throw new Error(`timed out waiting for ${what} to finish loading`);
    },
    async go(hash) {
      const before = errors.length;
      w.location.hash = hash;
      await page.settle(hash);
      return errors.slice(before);
    },
    text: () => (w.document.querySelector("#main") || {}).textContent || "",
    problems() {
      const out = [];
      for (const p of page.$$("#main .warn")) if (/Something went wrong/.test(p.textContent)) out.push(p.textContent.trim().slice(0, 300));
      const toast = page.$("#toast");
      if (toast && !toast.hidden && toast.classList.contains("err")) out.push("toast: " + toast.textContent);
      return out;
    },
    click: el => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })),
    change(el, value) {
      if (value !== undefined) el.value = value;
      el.dispatchEvent(new w.Event("change", { bubbles: true }));
    },
    input(el, value) {
      el.value = value;
      el.dispatchEvent(new w.Event("input", { bubbles: true }));
    },
  };
  await waitFor(() => w.eval("typeof S !== 'undefined' && !!S.lib"), "library to load");
  return page;
}

export const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function waitFor(fn, what, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if (await fn()) return; } catch (e) { /* not ready yet */ }
    await sleep(40);
  }
  throw new Error("timed out waiting for " + what);
}

export async function api(base, path, body) {
  const r = await fetch(base + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}
