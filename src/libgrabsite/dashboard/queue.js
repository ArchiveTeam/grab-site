export class BatchingQueue {
	#callable;
	#minInterval;
	#queue = [];
	#timer = null;

	constructor(callable, minInterval) {
		this.#callable = callable;
		this.#minInterval = minInterval;
	}

	setMinInterval(ms) {
		this.#minInterval = ms;
	}

	push(item) {
		this.#queue.push(item);
		this.#timer ??= setTimeout(() => this.#run(), this.#minInterval);
	}

	callNow() {
		if (this.#timer !== null) {
			clearTimeout(this.#timer);
		}
		this.#run();
	}

	#run() {
		this.#timer = null;
		const items = this.#queue;
		this.#queue = [];
		this.#callable(items);
	}
}

export class Decayer {
	#initial;
	#multiplier;
	#max;
	#current;

	constructor(initial, multiplier, max) {
		this.#initial = initial;
		this.#multiplier = multiplier;
		this.#max = max;
		this.reset();
	}

	reset() {
		// The first decay() multiplies, so divide here to make it return `initial`.
		this.#current = this.#initial / this.#multiplier;
		return this.#current;
	}

	decay() {
		this.#current = Math.min(this.#current * this.#multiplier, this.#max);
		return this.#current;
	}
}
