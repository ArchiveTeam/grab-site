export const $ = (id) => document.getElementById(id);

/**
 * Create an element. Props are assigned as DOM properties, except `on`, which maps
 * event names to listeners. null/undefined props are skipped, so a safeHref() that
 * rejected a URL leaves the attribute unset. Null children are ignored.
 */
export const el = (tag, props, ...children) => {
	const node = document.createElement(tag);
	for (const [key, value] of Object.entries(props ?? {})) {
		if (value == null) {
			continue;
		}
		if (key === "on") {
			for (const [type, listener] of Object.entries(value)) {
				node.addEventListener(type, listener);
			}
		} else {
			node[key] = value;
		}
	}
	node.append(...children.filter((child) => child != null));
	return node;
};

export const hasText = (s) => typeof s === "string" && s.trim() !== "";

/** Returns the URL if it is http, https or ftp, else null. Grabber URLs are untrusted. */
export const safeHref = (url) => (typeof url === "string" && /^(https?|ftp):\/\//i.test(url) ? url : null);

/** Link to an untrusted URL. Opens in a new tab. */
export const link = (url, text, className) =>
	el("a", { href: safeHref(url), className, target: "_blank", rel: "noopener noreferrer" }, text);

/** RegExp from user input, or null while the input is not a valid pattern yet. */
export const tryRegExp = (source) => {
	try {
		return new RegExp(source);
	} catch {
		return null;
	}
};

/** Escape a string for use inside a regular expression. */
export const regExpEscape = (s) => s.replace(/[\\^$.*+?()[\]{}|\/-]/g, "\\$&");

export const formatInt = new Intl.NumberFormat("en-US");
export const formatTenths = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Copy text to the clipboard. The Clipboard API needs a secure origin, and gs-server is often reached over plain http. */
export const copyText = async (text) => {
	try {
		await navigator.clipboard.writeText(text);
		return;
	} catch {
		// Fall through to the legacy path.
	}
	const scratch = el("textarea", { value: text, readOnly: true });
	scratch.style.cssText = "position: fixed; opacity: 0;";
	document.body.append(scratch);
	scratch.select();
	document.execCommand("copy");
	scratch.remove();
};
