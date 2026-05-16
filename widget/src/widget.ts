/**
 * The Widget. Owns the Shadow DOM, the SSE stream, and the citation panel.
 *
 * Single-agent variant — the config endpoint returns one config; no
 * public_key lookup.
 */
import { AgentConfig, CitationData, getConfig, sendFeedback, streamQuery } from "./api";
import { widgetStyles } from "./styles";

interface AgentMessage {
  role: "agent";
  textParts: string[];
  citations: CitationData[];
  done: boolean;
  metaLatencyMs?: number;
  metaCostUsd?: number;
  queryLogId?: string;
  feedback?: "up" | "down";
  error?: string;
}
interface UserMessage { role: "user"; text: string; }
type Message = UserMessage | AgentMessage;

export class Widget {
  private shadow: ShadowRoot;
  private root: HTMLDivElement;
  private config: AgentConfig | null = null;
  private open = false;
  private messages: Message[] = [];
  private streaming = false;
  private abortController: AbortController | null = null;

  private panelEl: HTMLDivElement | null = null;
  private messagesEl: HTMLDivElement | null = null;
  private inputEl: HTMLTextAreaElement | null = null;
  private sendBtn: HTMLButtonElement | null = null;

  constructor(host: HTMLElement, private apiBase: string) {
    this.shadow = host.attachShadow({ mode: "closed" });
    this.root = document.createElement("div");
    this.shadow.appendChild(this.root);
    void this.init();
  }

  private async init() {
    try {
      this.config = await getConfig(this.apiBase);
    } catch {
      this.config = {
        name: "Assistant",
        color: "#0066ff",
        greeting: "Hi! Ask me anything.",
        placeholder: "Ask a question…",
        suggested_questions: [],
      };
    }
    const style = document.createElement("style");
    style.textContent = widgetStyles(this.config.color);
    this.shadow.appendChild(style);
    this.renderLauncher();
  }

  private renderLauncher() {
    const btn = document.createElement("button");
    btn.className = "launcher";
    btn.setAttribute("aria-label", "Open chat");
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7
                 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8
                 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
      </svg>`;
    btn.addEventListener("click", () => this.togglePanel());
    this.root.appendChild(btn);
  }

  private togglePanel() {
    this.open = !this.open;
    if (this.open) this.openPanel();
    else this.closePanel();
  }

  private openPanel() {
    const panel = document.createElement("div");
    panel.className = "panel";
    panel.innerHTML = `
      <div class="header">
        <span class="dot"></span>
        <span class="title">${escapeHtml(this.config!.name)}</span>
        <button class="close" aria-label="Close">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
      </div>
      <div class="messages"></div>
      <div class="input-row">
        <textarea rows="1" placeholder="${escapeHtml(this.config!.placeholder)}"></textarea>
        <button class="send" aria-label="Send">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14M13 6l6 6-6 6"/></svg>
        </button>
      </div>`;
    this.root.appendChild(panel);
    this.panelEl = panel;
    this.messagesEl = panel.querySelector(".messages")!;
    this.inputEl = panel.querySelector("textarea")!;
    this.sendBtn = panel.querySelector(".send")!;

    panel.querySelector(".close")!.addEventListener("click", () => this.togglePanel());
    this.sendBtn.addEventListener("click", () => this.submit());
    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.submit(); }
    });
    this.inputEl.addEventListener("input", () => this.autoresize());

    this.renderMessages();
    this.inputEl.focus();
  }

  private closePanel() {
    this.abortController?.abort();
    this.abortController = null;
    this.streaming = false;
    this.panelEl?.remove();
    this.panelEl = this.messagesEl = null;
    this.inputEl = null;
    this.sendBtn = null;
  }

  private autoresize() {
    if (!this.inputEl) return;
    this.inputEl.style.height = "auto";
    this.inputEl.style.height = `${Math.min(this.inputEl.scrollHeight, 120)}px`;
  }

  private renderMessages() {
    if (!this.messagesEl) return;
    this.messagesEl.replaceChildren();

    if (this.messages.length === 0) {
      const greeting = document.createElement("div");
      greeting.className = "greeting";
      greeting.textContent = this.config!.greeting;
      this.messagesEl.appendChild(greeting);

      if (this.config!.suggested_questions.length > 0) {
        const sug = document.createElement("div");
        sug.className = "suggestions";
        for (const q of this.config!.suggested_questions) {
          const b = document.createElement("button");
          b.className = "suggestion";
          b.textContent = q;
          b.addEventListener("click", () => {
            if (this.inputEl) { this.inputEl.value = q; this.submit(); }
          });
          sug.appendChild(b);
        }
        this.messagesEl.appendChild(sug);
      }
    }

    for (let i = 0; i < this.messages.length; i++) this.renderMessage(i);
    this.scrollToBottom();
  }

  private renderMessage(idx: number) {
    if (!this.messagesEl) return;
    const m = this.messages[idx];
    const el = document.createElement("div");
    el.className = `msg ${m.role}`;
    el.dataset.idx = String(idx);

    if (m.role === "user") el.textContent = m.text;
    else this.renderAgentMessageInto(el, m);

    const existing = this.messagesEl.querySelector(`[data-idx="${idx}"]`);
    if (existing) existing.replaceWith(el);
    else this.messagesEl.appendChild(el);
  }

  private renderAgentMessageInto(el: HTMLDivElement, m: AgentMessage) {
    if (m.error) {
      el.className = "error";
      el.textContent = `Something went wrong: ${m.error}`;
      return;
    }
    const textContainer = document.createElement("div");
    const text = m.textParts.join("");
    const badgesByN = new Map(m.citations.map((c) => [c.n, c]));
    const parts = text.split(/(\[SOURCE\s+\d+\])/g);
    for (const part of parts) {
      const match = part.match(/^\[SOURCE\s+(\d+)\]$/);
      if (match) {
        const n = parseInt(match[1], 10);
        const cite = badgesByN.get(n);
        if (cite) {
          const badge = document.createElement("button");
          badge.className = "citation-badge";
          badge.textContent = String(n);
          badge.title = cite.source_title ?? "View source";
          badge.addEventListener("click", () => this.openSourcePanel(cite));
          textContainer.appendChild(badge);
          continue;
        }
      }
      if (part) textContainer.appendChild(document.createTextNode(part));
    }
    if (!m.done) {
      const cursor = document.createElement("span");
      cursor.className = "typing-cursor";
      textContainer.appendChild(cursor);
    }
    el.appendChild(textContainer);

    if (m.done && m.metaLatencyMs != null) {
      const meta = document.createElement("div");
      meta.className = "agent-meta";
      const lat = document.createElement("span");
      lat.className = "chip";
      lat.textContent = `${m.metaLatencyMs}ms`;
      meta.appendChild(lat);
      if (m.metaCostUsd != null && m.metaCostUsd > 0) {
        const cost = document.createElement("span");
        cost.className = "chip";
        cost.textContent = `$${m.metaCostUsd.toFixed(4)}`;
        meta.appendChild(cost);
      }
      const feedback = document.createElement("div");
      feedback.className = "feedback";
      for (const dir of ["up", "down"] as const) {
        const fb = document.createElement("button");
        fb.title = dir === "up" ? "Helpful" : "Not helpful";
        if (m.feedback === dir) fb.classList.add("selected");
        fb.innerHTML = dir === "up"
          ? `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12M15 5.88L14 10h5.83a2 2 0 0 1 1.92 2.56l-2.4 8A2 2 0 0 1 17.43 22H7M7 10H3v12h4"/></svg>`
          : `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2M9 18.12L10 14H4.17a2 2 0 0 1-1.92-2.56l2.4-8A2 2 0 0 1 6.57 2H17M17 14h4V2h-4"/></svg>`;
        fb.addEventListener("click", () => this.sendFeedbackFor(m, dir));
        feedback.appendChild(fb);
      }
      meta.appendChild(feedback);
      el.appendChild(meta);
    }
  }

  private scrollToBottom() {
    if (this.messagesEl) this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
  }

  private async submit() {
    if (!this.inputEl || this.streaming) return;
    const text = this.inputEl.value.trim();
    if (!text) return;

    this.messages.push({ role: "user", text });
    const agentMsg: AgentMessage = { role: "agent", textParts: [], citations: [], done: false };
    this.messages.push(agentMsg);

    this.inputEl.value = "";
    this.autoresize();
    this.streaming = true;
    if (this.sendBtn) this.sendBtn.disabled = true;
    this.renderMessages();

    this.abortController = new AbortController();
    const idx = this.messages.length - 1;

    try {
      await streamQuery(this.apiBase, text, {
        signal: this.abortController.signal,
        onText: (chunk) => {
          agentMsg.textParts.push(chunk);
          this.renderMessage(idx);
          this.scrollToBottom();
        },
        onCite: (cite) => { agentMsg.citations.push(cite); this.renderMessage(idx); },
        onDone: (data) => {
          agentMsg.done = true;
          agentMsg.metaLatencyMs = data.latency_ms;
          agentMsg.metaCostUsd = data.cost_usd;
          agentMsg.queryLogId = data.query_log_id;
          this.renderMessage(idx);
        },
        onError: (data) => {
          agentMsg.error = data.message;
          agentMsg.done = true;
          this.renderMessage(idx);
        },
      });
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        agentMsg.error = String(e);
        agentMsg.done = true;
        this.renderMessage(idx);
      }
    } finally {
      this.streaming = false;
      if (this.sendBtn) this.sendBtn.disabled = false;
      this.inputEl?.focus();
    }
  }

  private async sendFeedbackFor(m: AgentMessage, dir: "up" | "down") {
    if (!m.queryLogId) return;
    m.feedback = dir;
    const idx = this.messages.indexOf(m);
    if (idx >= 0) this.renderMessage(idx);
    try { await sendFeedback(this.apiBase, m.queryLogId, dir); } catch { /* best-effort */ }
  }

  private openSourcePanel(cite: CitationData) {
    const backdrop = document.createElement("div");
    backdrop.className = "source-panel-backdrop";
    const close = () => { backdrop.remove(); panel.remove(); };
    backdrop.addEventListener("click", close);

    const panel = document.createElement("div");
    panel.className = "source-panel";
    const titleLabel = cite.source_title ?? "Source";
    panel.innerHTML = `
      <header>
        <div class="num">${cite.n}</div>
        <div class="label">
          ${escapeHtml(titleLabel)}
          ${cite.source_url ? `<a class="url" href="${escapeAttr(cite.source_url)}" target="_blank" rel="noopener">${escapeHtml(cite.source_url)}</a>` : ""}
        </div>
        <button class="close" aria-label="Close">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
      </header>
      <div class="body"></div>`;
    panel.querySelector(".close")!.addEventListener("click", close);

    const body = panel.querySelector(".body") as HTMLDivElement;
    body.appendChild(renderHighlighted(cite));

    this.root.appendChild(backdrop);
    this.root.appendChild(panel);
  }
}

function renderHighlighted(cite: CitationData): DocumentFragment {
  const frag = document.createDocumentFragment();
  const { text, highlight_start: s, highlight_end: e } = cite;
  const valid = Number.isInteger(s) && Number.isInteger(e) && s < e && e <= text.length;
  if (!valid) { frag.appendChild(document.createTextNode(text)); return frag; }
  if (s > 0) frag.appendChild(document.createTextNode(text.slice(0, s)));
  const mark = document.createElement("mark");
  mark.textContent = text.slice(s, e);
  frag.appendChild(mark);
  if (e < text.length) frag.appendChild(document.createTextNode(text.slice(e)));
  return frag;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function escapeAttr(s: string): string { return escapeHtml(s); }
