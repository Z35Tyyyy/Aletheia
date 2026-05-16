/**
 * CSS for the widget's Shadow DOM root. Returned as a string so the widget
 * can inject it via a <style> tag inside the Shadow root.
 *
 * Design notes:
 *  - IBM Plex Sans (loaded from Google Fonts inside the Shadow root) for body,
 *    IBM Plex Mono for citation badges and timing chips.
 *  - Single accent color from the agent's UI config; everything else neutral.
 *  - Refined-minimal aesthetic: white surface, fine 1px hairlines, no heavy
 *    shadows, subtle motion. The host page's CSS can't reach this — see the
 *    "Comic Sans" hostility in index.html and how the widget ignores it.
 *  - Side panel slides in from the right with a soft backdrop; the cited
 *    sentence is wrapped in a <mark> with a tinted highlight.
 */

export function widgetStyles(accent: string): string {
  return `
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

    :host {
      all: initial;
      --accent: ${accent};
      --bg: #ffffff;
      --surface: #fafafa;
      --ink: #1a1a1a;
      --ink-soft: #5a5a5a;
      --ink-faint: #8a8a8a;
      --hairline: #e5e5e5;
      --highlight: ${accent}22;
      --highlight-bar: ${accent};
      font-family: "IBM Plex Sans", system-ui, sans-serif;
      font-size: 14px;
      color: var(--ink);
      line-height: 1.5;
    }

    *, *::before, *::after { box-sizing: border-box; }

    button {
      font-family: inherit;
      font-size: inherit;
      color: inherit;
      background: none;
      border: none;
      cursor: pointer;
      padding: 0;
    }

    /* ----- Launcher (FAB) ----- */
    .launcher {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 56px;
      height: 56px;
      border-radius: 28px;
      background: var(--ink);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 4px rgba(0, 0, 0, 0.08);
      transition: transform 0.18s ease, box-shadow 0.18s ease;
      z-index: 2147483646;
    }
    .launcher:hover { transform: translateY(-2px); box-shadow: 0 12px 32px rgba(0, 0, 0, 0.16); }
    .launcher svg { width: 22px; height: 22px; }

    /* ----- Panel ----- */
    .panel {
      position: fixed;
      bottom: 96px;
      right: 24px;
      width: 380px;
      max-width: calc(100vw - 48px);
      height: 560px;
      max-height: calc(100vh - 120px);
      background: var(--bg);
      border-radius: 12px;
      border: 1px solid var(--hairline);
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12), 0 4px 12px rgba(0, 0, 0, 0.04);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      z-index: 2147483645;
      transform-origin: bottom right;
      animation: pop-in 0.22s cubic-bezier(0.2, 0.8, 0.2, 1);
    }
    @keyframes pop-in {
      from { opacity: 0; transform: translateY(8px) scale(0.98); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .header {
      padding: 14px 16px;
      border-bottom: 1px solid var(--hairline);
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .header .dot {
      width: 8px;
      height: 8px;
      border-radius: 4px;
      background: var(--accent);
    }
    .header .title {
      font-weight: 600;
      letter-spacing: -0.01em;
      flex: 1;
    }
    .header .close {
      color: var(--ink-faint);
      width: 24px;
      height: 24px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .header .close:hover { background: var(--surface); color: var(--ink); }

    /* ----- Messages scroll area ----- */
    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .messages::-webkit-scrollbar { width: 6px; }
    .messages::-webkit-scrollbar-thumb { background: var(--hairline); border-radius: 3px; }

    .msg {
      max-width: 90%;
      padding: 10px 13px;
      border-radius: 10px;
      font-size: 14px;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
    .msg.user {
      align-self: flex-end;
      background: var(--ink);
      color: #fff;
      border-bottom-right-radius: 3px;
    }
    .msg.agent {
      align-self: flex-start;
      background: var(--surface);
      border: 1px solid var(--hairline);
      border-bottom-left-radius: 3px;
    }
    .msg.agent .citation-badge {
      display: inline-block;
      min-width: 18px;
      height: 18px;
      padding: 0 5px;
      border-radius: 9px;
      background: var(--accent);
      color: #fff;
      font-family: "IBM Plex Mono", monospace;
      font-size: 11px;
      font-weight: 500;
      text-align: center;
      line-height: 18px;
      margin: 0 2px;
      vertical-align: 1px;
      cursor: pointer;
      transition: transform 0.12s;
    }
    .msg.agent .citation-badge:hover { transform: scale(1.1); }

    .greeting {
      font-size: 13px;
      color: var(--ink-soft);
      padding: 8px 0;
    }
    .suggestions {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 8px;
    }
    .suggestion {
      text-align: left;
      padding: 8px 12px;
      border: 1px solid var(--hairline);
      border-radius: 8px;
      font-size: 13px;
      color: var(--ink-soft);
      transition: background 0.12s, color 0.12s, border-color 0.12s;
    }
    .suggestion:hover { background: var(--surface); color: var(--ink); border-color: var(--ink-faint); }

    .agent-meta {
      margin-top: 4px;
      display: flex;
      gap: 6px;
      align-items: center;
      font-family: "IBM Plex Mono", monospace;
      font-size: 11px;
      color: var(--ink-faint);
    }
    .agent-meta .chip {
      padding: 2px 6px;
      border-radius: 3px;
      background: var(--surface);
      border: 1px solid var(--hairline);
    }
    .agent-meta .feedback {
      margin-left: auto;
      display: flex;
      gap: 4px;
    }
    .agent-meta .feedback button {
      width: 22px; height: 22px;
      border-radius: 4px;
      color: var(--ink-faint);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .agent-meta .feedback button:hover { background: var(--surface); color: var(--ink); }
    .agent-meta .feedback button.selected { color: var(--accent); background: var(--highlight); }

    /* ----- Input ----- */
    .input-row {
      border-top: 1px solid var(--hairline);
      padding: 10px;
      display: flex;
      align-items: flex-end;
      gap: 8px;
      background: var(--bg);
    }
    .input-row textarea {
      flex: 1;
      min-height: 36px;
      max-height: 120px;
      resize: none;
      border: 1px solid var(--hairline);
      border-radius: 8px;
      padding: 8px 10px;
      font: inherit;
      color: inherit;
      outline: none;
      background: var(--bg);
    }
    .input-row textarea:focus { border-color: var(--accent); }
    .input-row .send {
      width: 36px; height: 36px;
      border-radius: 8px;
      background: var(--accent);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .input-row .send:disabled { opacity: 0.4; cursor: not-allowed; }

    /* ----- Source side panel ----- */
    .source-panel-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.18);
      z-index: 2147483646;
      animation: fade-in 0.18s ease;
    }
    @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }

    .source-panel {
      position: fixed;
      top: 0; right: 0; bottom: 0;
      width: min(460px, 88vw);
      background: var(--bg);
      box-shadow: -16px 0 40px rgba(0, 0, 0, 0.08);
      z-index: 2147483647;
      display: flex;
      flex-direction: column;
      animation: slide-in 0.24s cubic-bezier(0.2, 0.8, 0.2, 1);
    }
    @keyframes slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }

    .source-panel header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--hairline);
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .source-panel header .num {
      width: 24px; height: 24px;
      border-radius: 12px;
      background: var(--accent);
      color: #fff;
      font-family: "IBM Plex Mono", monospace;
      font-weight: 500;
      font-size: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .source-panel header .label {
      flex: 1;
      font-size: 13px;
      color: var(--ink-soft);
    }
    .source-panel header .url {
      display: block;
      font-family: "IBM Plex Mono", monospace;
      font-size: 11px;
      color: var(--accent);
      text-decoration: none;
      word-break: break-all;
    }
    .source-panel header .url:hover { text-decoration: underline; }
    .source-panel header .close {
      color: var(--ink-faint);
      width: 28px; height: 28px;
      border-radius: 4px;
      display: flex; align-items: center; justify-content: center;
    }
    .source-panel header .close:hover { background: var(--surface); color: var(--ink); }

    .source-panel .body {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      font-size: 14px;
      line-height: 1.65;
      color: var(--ink);
      white-space: pre-wrap;
    }
    .source-panel .body mark {
      background: var(--highlight);
      border-left: 3px solid var(--highlight-bar);
      padding: 2px 4px 2px 6px;
      margin-left: -6px;
      border-radius: 0 3px 3px 0;
    }

    /* ----- Cursor ----- */
    .typing-cursor {
      display: inline-block;
      width: 1px;
      height: 0.9em;
      background: currentColor;
      vertical-align: -1px;
      margin-left: 1px;
      animation: blink 0.9s steps(1) infinite;
    }
    @keyframes blink { 50% { opacity: 0; } }

    /* ----- Error ----- */
    .error {
      align-self: stretch;
      background: #fff5f5;
      color: #aa1111;
      border: 1px solid #ffd9d9;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13px;
    }
  `;
}
