// The main navigation on the server. Nav takes the current path as a prop, so
// these tests need only a stand-in for $app/paths. The stand-in adds a /la base,
// so a link that skips resolve() fails here.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { test } from 'node:test';
import { parseHTML } from 'linkedom';
import { render } from 'svelte/server';
import { NAV, isCurrent, type NavItem } from '../src/lib/nav.ts';

registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier !== '$app/paths') return nextResolve(specifier, context);
		return {
			url: `data:text/javascript,${encodeURIComponent("export const resolve = (path) => '/la' + (path === '/' ? '' : path);")}`,
			shortCircuit: true
		};
	}
});

const { default: Nav } = await import('../src/lib/design/Nav.svelte');

function links(route: string | null, items?: readonly NavItem[]) {
	const { body } = render(Nav, { props: { route, items } });
	const { document } = parseHTML(`<!doctype html><html><body>${body}</body></html>`);
	const navs = [...document.querySelectorAll('nav')];
	return {
		navs,
		anchors: [...document.querySelectorAll('nav a')].map((a) => ({
			text: a.textContent.trim(),
			href: a.getAttribute('href'),
			current: a.getAttribute('aria-current')
		}))
	};
}

test('the list names the four entries in order', () => {
	assert.deepEqual(
		NAV.map((item) => [item.label, item.path + (item.hash ?? '')]),
		[
			['Find a line', '/#search'],
			['Ranking', '/ranking'],
			['Methods', '/methods'],
			['Behind the scenes', '/behind-the-scenes']
		]
	);
	for (const item of NAV) assert.equal(typeof item.ready, 'boolean', item.label);
});

test('the default list renders the ready entries in order, with the base in each link', () => {
	const { navs, anchors } = links('/ranking');
	assert.equal(navs.length, 1);
	assert.equal(navs[0].getAttribute('aria-label'), 'Main');
	const ready = NAV.filter((item) => item.ready);
	assert.deepEqual(
		anchors.map((a) => a.text),
		ready.map((item) => item.label)
	);
	assert.deepEqual(
		anchors.map((a) => a.href),
		ready.map((item) => `/la${item.path === '/' ? '' : item.path}${item.hash ?? ''}`)
	);
});

test('Behind the scenes is drawn and marked on its own page', () => {
	const { anchors } = links('/behind-the-scenes');
	assert.deepEqual(
		anchors.map((a) => a.text),
		['Find a line', 'Ranking', 'Methods', 'Behind the scenes']
	);
	const current = anchors.filter((a) => a.current === 'page');
	assert.deepEqual(
		current.map((a) => [a.text, a.href]),
		[['Behind the scenes', '/la/behind-the-scenes']]
	);
});

test('an entry that is not ready is not rendered', () => {
	const items: NavItem[] = [
		{ label: 'One', path: '/', hash: '#search', ready: true },
		{ label: 'Two', path: '/ranking', ready: false },
		{ label: 'Three', path: '/methods', ready: true }
	];
	assert.deepEqual(
		links('/', items).anchors.map((a) => a.text),
		['One', 'Three']
	);
	items[1].ready = true;
	assert.deepEqual(
		links('/', items).anchors.map((a) => a.text),
		['One', 'Two', 'Three']
	);
});

test('the link for the current path has aria-current and no other does', () => {
	const ready = NAV.filter((item) => item.ready);
	for (const item of ready) {
		const { anchors } = links(item.path);
		const current = anchors.filter((a) => a.current === 'page').map((a) => a.text);
		assert.deepEqual(current, [item.label], item.path);
	}
	assert.equal(links('/lines/[line]').anchors.filter((a) => a.current).length, 0);
});

test('a route that is not in the list marks nothing, and the base never matters', () => {
	assert.equal(isCurrent(NAV[1], '/ranking'), true);
	assert.equal(isCurrent(NAV[1], '/ranking-old'), false);
	assert.equal(isCurrent(NAV[1], '/la/ranking'), false);
	assert.equal(isCurrent(NAV[1], null), false);
	assert.equal(links(null).anchors.filter((a) => a.current).length, 0);
});
