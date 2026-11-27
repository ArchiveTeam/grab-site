import { ContextMenu } from "./context-menu.js";
import { BatchingQueue, Decayer } from "./queue.js";
import { JobsRenderer, URL_LINK_SELECTOR } from "./renderer.js";
import { THEMES, readStoredTheme, writeStoredTheme } from "./theme.js";
import { $, el } from "./util.js";

class Dashboard {
	#host;
	#dumpMax;
	#messageCount = 0;
	#menu;
	#renderer;
	#queue;
	#decayer = new Decayer(1000, 1.5, 60000);
	#batchTimeWhenVisible;
	#batchTimeWhenHidden = 5000;
	#theme = readStoredTheme();

	constructor() {
		const args = new URLSearchParams(location.search);
		const arg = (name, fallback, parse) => (args.get(name) ? parse(args.get(name)) : fallback);
		const historyLines = arg("historyLines", navigator.userAgent.includes("Mobi") ? 250 : 1000, Number);
		const showNicks = arg("showNicks", false, (v) => Boolean(Number(v)));
		const contextMenu = arg("contextMenu", true, (v) => Boolean(Number(v)));
		const moreDom = arg("moreDom", false, (v) => Boolean(Number(v)));
		this.#batchTimeWhenVisible = arg("batchTimeWhenVisible", 125, Number);
		// Append to the page title to make it possible to identify the tab in Chrome's task manager.
		if (args.get("title")) {
			document.title += " - " + args.get("title");
		}
		// If no ?host=, connect to this grab-site server instead of some other server.
		this.#host = args.get("host") || location.host;
		this.#dumpMax = Number(args.get("dumpMax")) || 0;

		document.querySelectorAll(".url-q-or-amp").forEach((e) => {
			e.textContent = location.search ? "&" : "?";
		});

		this.#menu = new ContextMenu($("context-menu"));
		this.#renderer = new JobsRenderer({
			container: $("logs"),
			filterBox: $("filter-box"),
			numCrawls: $("num-crawls"),
			historyLines,
			showNicks,
			moreDom,
			menu: this.#menu,
		});
		this.#queue = new BatchingQueue((items) => {
			for (const raw of items) {
				this.#handleMessage(JSON.parse(raw));
			}
		}, this.#batchTimeWhenVisible);

		this.#applyTheme();
		this.#bindEvents(contextMenu);
		this.#connect();
	}

	#bindEvents(contextMenu) {
		document.addEventListener("keydown", (ev) => this.#onKeyDown(ev));
		document.addEventListener("click", (ev) => this.#onClick(ev));
		document.addEventListener("visibilitychange", () => {
			if (document.hidden) {
				this.#queue.setMinInterval(this.#batchTimeWhenHidden);
			} else {
				this.#queue.setMinInterval(this.#batchTimeWhenVisible);
				this.#queue.callNow();
			}
		});
		if (contextMenu) {
			document.addEventListener("contextmenu", (ev) => this.#onContextMenu(ev));
			document.addEventListener("wheel", () => this.#menu.close(), { passive: true });
		}
	}

	#onKeyDown(ev) {
		if (ev.ctrlKey || ev.altKey || ev.metaKey) {
			return;
		}
		// Typing in the filter box must not trigger shortcuts.
		if (ev.target === $("filter-box")) {
			return;
		}
		if (ev.key === "?") {
			this.#toggleHelp();
			return;
		}
		if (ev.shiftKey) {
			return;
		}
		switch (ev.key) {
			case "j": this.#renderer.showNextPrev(1); break;
			case "k": this.#renderer.showNextPrev(-1); break;
			case "a": this.#renderer.setFilter(""); break;
			case "n": this.#renderer.setFilter("^$"); break;
			case "f":
				ev.preventDefault();
				$("filter-box").focus();
				$("filter-box").select();
				break;
			case "v": this.#renderer.openFirstMatch(); break;
		}
	}

	#onClick(ev) {
		if (!(ev.target instanceof Element)) {
			return;
		}
		const button = ev.target.closest("[data-action], [data-filter]");
		if (!button) {
			return;
		}
		if (button.dataset.filter !== undefined) {
			this.#renderer.setFilter(button.dataset.filter);
		} else if (button.dataset.action === "align") {
			this.#renderer.toggleAlign();
		} else if (button.dataset.action === "help") {
			this.#toggleHelp();
		} else if (button.dataset.action === "theme") {
			this.#cycleTheme();
		}
	}

	#onContextMenu(ev) {
		const a = ev.target instanceof Element ? ev.target.closest("a") : null;
		const isUrl = a !== null && a.matches(URL_LINK_SELECTOR) && a.closest(".log-window") && a.href;
		if (!isUrl) {
			this.#menu.close();
			return;
		}
		ev.preventDefault();
		this.#menu.open(a.href, ev.clientX, ev.clientY);
	}

	#toggleHelp() {
		const help = $("help");
		help.hidden = !help.hidden;
		document.querySelector("[data-action=help]").setAttribute("aria-expanded", String(!help.hidden));
	}

	#cycleTheme() {
		const next = THEMES[(THEMES.indexOf(this.#theme) + 1) % THEMES.length];
		this.#theme = next;
		writeStoredTheme(next);
		this.#applyTheme();
	}

	#applyTheme() {
		const root = document.documentElement;
		if (this.#theme === "auto") {
			delete root.dataset.theme;
		} else {
			root.dataset.theme = this.#theme;
		}
		document.querySelector("[data-action=theme]").textContent = `Theme: ${this.#theme}`;
	}

	#handleMessage(data) {
		this.#messageCount += 1;
		if (this.#messageCount <= this.#dumpMax) {
			$("traffic").append(el("pre", { textContent: JSON.stringify(data, undefined, 2) }));
		}
		this.#renderer.handleData(data);
	}

	#connect() {
		// Use wss:// if we're behind a reverse proxy serving with https://
		const protocol = location.protocol === "https:" ? "wss:" : "ws:";
		const ws = new WebSocket(`${protocol}//${this.#host}/stream`);

		ws.onmessage = (ev) => this.#queue.push(ev.data);

		ws.onopen = (ev) => {
			console.log("WebSocket opened:", ev);
			ws.send(JSON.stringify({
				type: "hello",
				mode: "dashboard",
				user_agent: navigator.userAgent,
			}));
			this.#decayer.reset();
		};

		ws.onclose = (ev) => {
			console.log("WebSocket closed:", ev);
			const delay = this.#decayer.decay();
			console.log("Reconnecting in", delay, "ms");
			setTimeout(() => this.#connect(), delay);
		};
	}
}

new Dashboard();
