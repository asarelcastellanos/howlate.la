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
