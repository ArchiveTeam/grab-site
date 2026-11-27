import { JobsTracker } from "./jobs.js";
import { el, formatInt, formatTenths, hasText, link, regExpEscape, safeHref, tryRegExp } from "./util.js";

const FATAL_LINE_RE = /^Finished grab \S+ \S+ with exit code |^CRITICAL (Sorry|Please report)|^ERROR Fatal exception|No space left on device|^Fatal Python error:|^(Thread|Current thread) 0x/;
const FINISHED_LINE_RE = /^Finished grab \S+ \S+ with exit code ([0-13-8])$/;
export const URL_LINK_SELECTOR = ".line-normal, .line-error, .line-warning, .line-redirect, .log-url";

const totalResponses = (job) =>
	["r1xx", "r2xx", "r3xx", "r4xx", "r5xx", "runk"].reduce((sum, key) => sum + parseInt(job[key]), 0);

const responseSummary = (job) =>
	[["1xx", "r1xx"], ["2xx", "r2xx"], ["3xx", "r3xx"], ["4xx", "r4xx"], ["5xx", "r5xx"], ["Unknown", "runk"]]
		.map(([label, key]) => `${label}: ${formatInt.format(job[key])}`)
		.join("\n");

const lineClassFor = (code) => {
	if (code >= 400 && code < 500) {
		return "line-warning";
	}
	if (code === 0 || code >= 500) {
		return "line-error";
	}
	if (code && code >= 300 && code < 400) {
		return "line-redirect";
	}
	return "line-normal";
};

export class JobsRenderer {
	#container;
	#filterBox;
	#numCrawls;
	#menu;
	#moreDom;
	#historyLines;
	#linesPerSegment;
	#jobs = new JobsTracker();
	/** ident -> per-job DOM and line-count state */
	#info = new Map();
	#mouseInside = null;
	#firstFilterMatch = null;
	#aligned = false;

	constructor({ container, filterBox, numCrawls, historyLines, showNicks, moreDom, menu }) {
		this.#container = container;
		this.#filterBox = filterBox;
		this.#numCrawls = numCrawls;
		this.#menu = menu;
		this.#moreDom = moreDom;
		this.#historyLines = historyLines;
		this.#linesPerSegment = Math.max(1, Math.round(historyLines / 10));
		container.classList.toggle("show-nicks", showNicks);
		filterBox.addEventListener("input", () => this.applyFilter());
	}

	handleData(data) {
		const job = data.job_data;
		const added = this.#jobs.add(job);
		this.#updateCrawlCount();
		if (added) {
			this.#createLogContainer(job);
		}
		const info = this.#info.get(job.ident);

		let linesRendered;
		switch (data.type) {
			case "download":
				linesRendered = this.#renderDownload(data, info.logSegment);
				break;
			case "stdout":
			case "stderr":
				linesRendered = this.#renderStdout(data.message, info, job.ident);
				break;
			case "ignore":
				linesRendered = this.#renderIgnore(data, info.logSegment);
				break;
			default:
				throw new Error(`Unexpected message type ${data.type}`);
		}

		this.#updateStats(job, info);
		this.#updateLineCounts(info, job.ident, linesRendered);
	}

	applyFilter() {
		const re = tryRegExp(this.#filterBox.value);
		// An invalid pattern matches nothing until it is fixed.
		this.#filterBox.setAttribute("aria-invalid", String(re === null));

		this.#firstFilterMatch = null;
		const matchedWindows = [];
		for (const job of this.#jobs.sorted) {
			const { logWindow } = this.#info.get(job.ident);
			const matched = re !== null && re.test(job.url);
			logWindow.classList.toggle("log-window-hidden", !matched);
			logWindow.classList.remove("log-window-expanded");
			if (!matched) {
				logWindow.classList.remove("log-window-stopped");
			} else {
				matchedWindows.push(logWindow);
				this.#firstFilterMatch ??= job;
			}
		}

		// If only one window is visible, expand it so more lines are visible.
		if (matchedWindows.length === 1) {
			matchedWindows[0].classList.add("log-window-expanded");
		}

		// With few windows shown, alignment helps more than full stats do.
		this.#aligned = matchedWindows.length < this.#jobs.sorted.length;
		this.#updateAlign();
	}

	setFilter(value) {
		this.#filterBox.value = value;
		this.applyFilter();
	}

	showNextPrev(offset) {
		const jobs = this.#jobs.sorted;
		const n = jobs.length;
		let idx = jobs.findIndex((job) => job.ident === this.#firstFilterMatch?.ident);
		// Nothing shown yet: j goes to the first window, k to the last.
		if (idx === -1) {
			idx = n;
		}
		idx += offset;
		// Past either end, hide all windows; going past the hidden state wraps around.
		if (idx === -1) {
			idx = n;
		} else if (idx === n + 1) {
			idx = 0;
		}
		this.setFilter(idx === n ? "^$" : `^${regExpEscape(jobs[idx].url)}$`);
	}

	openFirstMatch() {
		const url = safeHref(this.#firstFilterMatch?.url);
		if (url !== null) {
			window.open(url, "_blank", "noopener");
		}
	}

	toggleAlign() {
		this.#aligned = !this.#aligned;
		this.#updateAlign();
	}

	#updateAlign() {
		this.#container.classList.toggle("aligned", this.#aligned);
		document.querySelector("[data-action=align]").setAttribute("aria-pressed", String(this.#aligned));
	}

	#updateCrawlCount() {
		const n = this.#jobs.activeCount;
		this.#numCrawls.textContent = n === 1 ? "1 crawl" : `${n} crawls`;
	}

	#toggleFilterFor(url) {
		const filter = this.#filterBox.value;
		const isOnlyThisJob = tryRegExp(filter)?.test(url) && filter.startsWith("^") && filter.endsWith("$");
		// If this job is already the only one shown, clicking again shows nothing.
		this.setFilter(isOnlyThisJob ? "^$" : `^${regExpEscape(url)}$`);
	}

	#createLogContainer(job) {
		const { ident } = job;
		const logSegment = el("div");
		const logWindow = el("div", { className: "log-window" });
		logWindow.addEventListener("mouseenter", () => {
			this.#mouseInside = ident;
			logWindow.classList.add("log-window-stopped");
		});
		logWindow.addEventListener("mouseleave", () => {
			const leave = () => {
				this.#mouseInside = null;
				logWindow.classList.remove("log-window-stopped");
			};
			// Opening the context menu moves the mouse out of the window; wait for it to close.
			if (this.#menu.isOpen) {
				this.#menu.afterClose(leave);
			} else {
				leave();
			}
		});

		const stats = {
			mb: el("span", { className: "inline-stat job-mb" }, "?"),
			responses: el("span", { className: "inline-stat job-responses" }, "?"),
			responsesPerSecond: el("span", { className: "inline-stat job-responses-per-second" }, "?"),
			queueLength: el("span", { className: "inline-stat job-in-queue" }, "? in q."),
			connections: el("span", { className: "inline-stat job-connections" }, "?"),
			delay: el("span", { className: "inline-stat job-delay" }, "? ms delay"),
			ignores: el("span", { className: "job-ignores" }, "?"),
		};

		const startedISO = new Date(parseFloat(job.started_at) * 1000).toISOString();
		const note = el("span", { className: "job-note" });
		const jobInfo = el("span", { className: "job-info" },
			link(job.url, job.url, "inline-stat job-url"),
			// Clicking anywhere in this area shows just this job's URL.
			el("span", { className: "stats-elements", on: { click: () => this.#toggleFilterFor(job.url) } },
				" on ",
				el("span", { className: "inline-stat", title: startedISO }, startedISO.split("T")[0].slice(5)),
				el("span", { className: "inline-stat job-nick" }, this.#showNicks ? ` by ${job.started_by}` : ""),
				note,
				"; ",
				stats.mb,
				" MB in ",
				stats.responses,
				" at ",
				stats.responsesPerSecond,
				"/s, ",
				stats.queueLength,
				"; ",
				stats.connections,
				" con. w/ ",
				stats.delay,
				"; ",
				stats.ignores,
			),
		);

		const container = el("div", { className: "job-card" },
			el("div", { className: "job-header" },
				jobInfo,
				el("input", {
					className: "job-ident",
					type: "text",
					value: ident,
					size: 28,
					spellcheck: false,
					readOnly: true,
					on: { click: (ev) => ev.currentTarget.select() },
				}),
			),
			logWindow,
		);

		this.#info.set(ident, {
			container,
			logWindow,
			logSegment,
			stats,
			jobInfo,
			note,
			lineCountWindow: 0,
			lineCountSegments: [0],
		});
		logWindow.append(logSegment);

		const idx = this.#jobs.sorted.findIndex((j) => j.ident === ident);
		const next = this.#jobs.sorted[idx + 1];
		this.#container.insertBefore(container, next ? this.#info.get(next.ident).container : null);
		this.#updateAlign();
		this.applyFilter();
	}

	get #showNicks() {
		return this.#container.classList.contains("show-nicks");
	}

	#renderDownload(data, logSegment) {
		const { response_code: code, wget_code: wget, url } = data;
		const lineClass = lineClassFor(code);
		if (this.#moreDom) {
			// Lets the user start a text selection from the left or right of the URL.
			logSegment.append(el("div", { className: `line ${lineClass}` }, `${code} ${wget} `, link(url, url, "log-url")));
		} else {
			logSegment.append(link(url, `${code} ${wget} ${url}`, `line ${lineClass}`));
		}
		return 1;
	}

	#renderIgnore(data, logSegment) {
		logSegment.append(el("div", { className: "line line-ignore" },
			el("span", null, " IGNOR "),
			link(data.url, data.url, "ignore"),
			el("span", { className: "bold" }, " by "),
			data.pattern,
		));
		return 1;
	}

	#renderStdout(message, info, ident) {
		let text = message.replace(/[\r\n]+$/, "");
		// Format DUPE/OF messages a little more nicely.
		text = text.replace(/^DUPE /, "  DUPE ").replace(/\n  OF /, "\n      OF ");

		let rendered = 0;
		for (const line of text.split("\n")) {
			if (!line) {
				continue;
			}
			info.logSegment.append(el("div", { className: "line line-stdout" }, line));
			rendered += 1;

			if (FINISHED_LINE_RE.test(line)) {
				info.jobInfo.classList.add("job-info-done");
				this.#jobs.markFinished(ident);
			} else if (FATAL_LINE_RE.test(line)) {
				info.jobInfo.classList.add("job-info-fatal");
				this.#jobs.markFatal(ident);
			} else if (/Script requested immediate stop/.test(line)) {
				// This can follow a fatal exception, so it replaces the fatal style.
				info.jobInfo.classList.remove("job-info-fatal");
				info.jobInfo.classList.add("job-info-aborted");
			}
		}
		return rendered;
	}

	#updateStats(job, info) {
		const s = info.stats;
		const total = totalResponses(job);

		s.mb.textContent = formatTenths.format(Number(job.bytes_downloaded) / (1024 * 1024));
		s.responses.textContent = `${formatInt.format(total)} resp.`;
		s.responses.title = responseSummary(job);
		const duration = Date.now() / 1000 - parseFloat(job.started_at);
		s.responsesPerSecond.textContent = (total / duration).toFixed(1);

		if (job.items_queued && job.items_downloaded) {
			const queued = parseInt(job.items_queued, 10);
			const downloaded = parseInt(job.items_downloaded, 10);
			s.queueLength.textContent = `${formatInt.format(queued - downloaded)} in q.`;
			s.queueLength.title = `${formatInt.format(queued)} queued\n${formatInt.format(downloaded)} downloaded`;
		}

		s.connections.textContent = job.concurrency;

		const min = parseInt(job.delay_min);
		const max = parseInt(job.delay_max);
		const delayText = min === max ? String(min) : `${min}-${max}`;
		s.delay.textContent = `${delayText} ms delay`;

		const suppressed = Boolean(job.suppress_ignore_reports);
		s.ignores.textContent = suppressed ? "igoff" : "igon";
		s.ignores.classList.toggle("job-igoff", suppressed);

		info.note.textContent = hasText(job.note) ? ` (${job.note})` : "";
	}

	#updateLineCounts(info, ident, linesRendered) {
		info.lineCountWindow += linesRendered;
		info.lineCountSegments[info.lineCountSegments.length - 1] += linesRendered;

		if (info.lineCountSegments[info.lineCountSegments.length - 1] >= this.#linesPerSegment) {
			const newSegment = el("div");
			info.logWindow.append(newSegment);
			info.logSegment = newSegment;
			info.lineCountSegments.push(0);
		}

		// Don't move the view while the user is looking at this window.
		if (this.#mouseInside === ident) {
			return;
		}
		// Keep scrollback for jobs with a fatal exception so the traceback can be found.
		if (!this.#jobs.hasFatal(ident)) {
			while (info.lineCountWindow >= this.#historyLines + this.#linesPerSegment) {
				info.logWindow.firstElementChild.remove();
				info.lineCountWindow -= info.lineCountSegments.shift();
			}
		}
		info.logWindow.scrollTop = 999999;
	}
}
