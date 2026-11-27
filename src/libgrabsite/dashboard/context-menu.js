import { copyText, el, link, regExpEscape, safeHref } from "./util.js";

/** Given a URL, returns the regexes that a --ignore pattern could use to match it. */
const suggestedCommands = (url) => {
	const u = new URL(url);
	const reScheme = u.protocol.startsWith("http") ? "https?" : "ftp";
	const paths = [u.pathname];
	let path = u.pathname.replace(/\/$/, "");
	while (path && path.includes("/")) {
		path = path.replace(/\/[^/]*$/, "");
		paths.push(path + "/");
	}
	return paths.map((p) => `^${reScheme}://${regExpEscape(u.host + p)}`);
};

export class ContextMenu {
	#el;
	#afterCloseFns = [];

	constructor(element) {
		this.#el = element;
		// Fires after the popover closes by any means: Escape, clicking outside, or close().
		element.addEventListener("toggle", (ev) => {
			if (ev.newState === "closed") {
				const fns = this.#afterCloseFns;
				this.#afterCloseFns = [];
				fns.forEach((fn) => fn());
			}
		});
	}

	get isOpen() {
		return this.#el.matches(":popover-open");
	}

	/** Run fn once the menu next closes. */
	afterClose(fn) {
		this.#afterCloseFns.push(fn);
	}

	close() {
		if (this.isOpen) {
			this.#el.hidePopover();
		}
	}

	open(url, x, y) {
		const copyEntry = (label, text) => el("button", {
			type: "button",
			className: "context-menu-entry",
			on: { click: () => { copyText(text); this.close(); } },
		}, label);
		this.#el.replaceChildren(
			el("a", {
				href: safeHref(url),
				className: "context-menu-entry",
				target: "_blank",
				rel: "noopener noreferrer",
				on: { click: () => this.close() },
			}, "Open link in new tab"),
			copyEntry("Copy link address", url),
			...suggestedCommands(url).map((command) => copyEntry(`Copy ${command}`, command)),
		);
		if (this.isOpen) {
			this.#el.hidePopover();
		}
		this.#el.style.left = `${x}px`;
		this.#el.style.top = `${y}px`;
		this.#el.showPopover();
		// If the bottom of the menu is outside the viewport, open it upwards instead.
		const height = this.#el.offsetHeight;
		if (y + height > document.documentElement.clientHeight) {
			this.#el.style.top = `${y - height + 1}px`;
		}
	}
}
