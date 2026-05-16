/**
 * Bootstrap. Reads `data-api` from the script tag and mounts a Widget.
 */
import { Widget } from "./widget";

function readApiBase(): string {
  const scripts = document.querySelectorAll("script[data-api]");
  const tag = scripts[scripts.length - 1] as HTMLScriptElement | undefined;
  return tag?.dataset.api ?? "http://localhost:8000";
}

function mount() {
  const apiBase = readApiBase();
  const host = document.createElement("div");
  host.id = "ragfast-widget-host";
  document.body.appendChild(host);
  new Widget(host, apiBase);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount, { once: true });
} else {
  mount();
}
