// Mounts ResultView in a DOM and checks that a component that throws while it
// renders leaves the error box and not a crash. The server build has no boundary
// that catches a render error, so this test runs the client build:
// `node --conditions=browser --import ./tests/client.mjs`.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseHTML } from 'linkedom';

const { window, document } = parseHTML('<!doctype html><html><body></body></html>');
// Svelte reads firstChild and nextSibling off Node.prototype. In linkedom that
// one returns null for an element, so the element versions stand in for it.
const own = (proto: object, name: string) => Object.getOwnPropertyDescriptor(proto, name)!;
const parentNode = Object.getPrototypeOf(window.Element.prototype);
class SvelteNode {}
Object.defineProperty(SvelteNode.prototype, 'firstChild', own(parentNode, 'firstChild'));
Object.defineProperty(
	SvelteNode.prototype,
	'nextSibling',
	own(window.Element.prototype, 'nextSibling')
);
Object.assign(globalThis, {
	window,
	document,
	Node: SvelteNode,
	Element: window.Element,
	HTMLElement: window.HTMLElement,
	HTMLTemplateElement: window.HTMLTemplateElement,
	Text: window.Text,
	Comment: window.Comment,
	DocumentFragment: window.DocumentFragment,
	Event: window.Event,
	CustomEvent: window.CustomEvent
});

// linkedom's <template> has no content, which Svelte clones its markup from.
const create = document.createElement.bind(document);
document.createElement = ((tag: string) => {
	const el = create(tag === 'template' ? 'div' : tag);
	if (tag === 'template') {
		Object.defineProperty(el, 'content', {
			// A div holds the same children, and Svelte only reads them from it.
			get: () => el
		});
	}
	return el;
}) as typeof document.createElement;

const { mount, flushSync } = await import('svelte');
const { default: Guarded } = await import('./fixtures/Guarded.svelte');

test('a component that throws while it renders shows the error box', () => {
	const target = document.createElement('div');
	document.body.append(target);
	mount(Guarded, { target });
	flushSync();
	assert.match(target.innerHTML, /role="alert"/);
	assert.match(target.innerHTML, /We couldn't load this data\./);
	assert.match(target.innerHTML, /Try again/);
});

const { default: Loads } = await import('./fixtures/Loads.svelte');
const settle = async () => {
	// Two ticks let the rejected or resolved promise reach the effect's callback.
	await new Promise((resolve) => setTimeout(resolve, 0));
	flushSync();
};

test('a load that rejects shows the error box with a retry that loads again', async () => {
	const target = document.createElement('div');
	document.body.append(target);
	let calls = 0;
	const load = async () => {
		calls++;
		if (calls === 1) throw new Error('a render or parse error outside the loader');
		return { ok: true as const, data: 'second try' };
	};
	mount(Loads, { target, props: { load } });
	flushSync();
	await settle();
	assert.match(target.innerHTML, /role="alert"/);
	assert.match(target.innerHTML, /We couldn't load this data\./);
	assert.doesNotMatch(target.innerHTML, /Loading the data/);
	const retry = target.querySelector('button');
	assert.ok(retry, 'the error state has a retry button');
	// Svelte stores a delegated click handler on the element under a private
	// symbol. linkedom does not give the event the path Svelte reads, so a
	// dispatched click never reaches it and the test calls the handler.
	const events = Object.getOwnPropertySymbols(retry).find((s) => String(s) === 'Symbol(events)');
	(retry as unknown as Record<symbol, { click: (e: Event) => void }>)[events!].click(
		new window.Event('click')
	);
	flushSync();
	await settle();
	assert.equal(calls, 2);
	assert.match(target.innerHTML, /second try/);
});

// Chart redraws on a width change and drops the old SVG. A keyboard user on the
// heatmap must stay on it. linkedom has no focus tracking, so the test supplies
// document.activeElement and an svg.focus that moves it, which is all Chart reads.
test('keyboard focus on a chart survives a redraw at a new width', async () => {
	const { default: Chart } = await import('../src/lib/charts/Chart.svelte');
	let active: unknown = null;
	Object.defineProperty(document, 'activeElement', { get: () => active, configurable: true });
	const watchers: ((entries: { contentRect: { width: number } }[]) => void)[] = [];
	Object.assign(globalThis, {
		ResizeObserver: class {
			constructor(callback: (entries: { contentRect: { width: number } }[]) => void) {
				watchers.push(callback);
			}
			observe() {}
			disconnect() {}
		}
	});
	const draws: Element[] = [];
	const render = (width: number) => {
		const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
		svg.setAttribute('width', String(width));
		svg.setAttribute('tabindex', '0');
		(svg as unknown as { focus: () => void }).focus = () => {
			active = svg;
		};
		draws.push(svg);
		return svg;
	};
	const target = document.createElement('div');
	document.body.append(target);
	mount(Chart, { target, props: { render, label: 'Heatmap', onrender: () => {} } });
	flushSync();
	const resize = (width: number) => {
		for (const watch of watchers) watch([{ contentRect: { width } }]);
		flushSync();
	};

	resize(300);
	assert.equal(draws.length, 1);
	assert.ok(active === null, 'a first draw does not take focus');

	active = draws[0];
	resize(400);
	assert.equal(draws.length, 2, 'the new width drew again');
	assert.ok(target.contains(draws[1]) && !target.contains(draws[0]));
	assert.ok(active === draws[1], 'focus moved to the new svg');

	active = null;
	resize(500);
	assert.equal(draws.length, 3);
	assert.ok(active === null, 'with no focus in the chart, a redraw does not take it');
});
