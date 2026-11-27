export class JobsTracker {
	/** Job data, newest first. */
	sorted = [];
	#known = new Set();
	#finished = new Set();
	#fatal = new Set();

	get activeCount() {
		return this.sorted.length - this.#finished.size;
	}

	/** Returns true if the job was not seen before. */
	add(job) {
		if (this.#known.has(job.ident)) {
			return false;
		}
		this.#known.add(job.ident);
		this.sorted.push(job);
		this.sorted.sort((a, b) => parseFloat(b.started_at) - parseFloat(a.started_at));
		return true;
	}

	markFinished(ident) {
		this.#finished.add(ident);
	}

	markFatal(ident) {
		this.#fatal.add(ident);
	}

	hasFatal(ident) {
		return this.#fatal.has(ident);
	}
}
