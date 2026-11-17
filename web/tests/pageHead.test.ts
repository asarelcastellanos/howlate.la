// PageHead on the server, then every route page that uses it. The pages import
// $app modules that exist only inside SvelteKit, so small stand-ins come first.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { test } from 'node:test';
import { parseHTML } from 'linkedom';
import { render } from 'svelte/server';
import { SITE_URL } from '../src/lib/config.ts';
import PageHead from '../src/lib/PageHead.svelte';

registerHooks({
	resolve(specifier, context, nextResolve) {
		const stubs: Record<string, string> = {
			'$app/paths': 'export const resolve = (path) => path;',
			'$app/navigation': 'export const goto = () => Promise.resolve();',
			'$app/state':
				"export const page = { params: { line: '720' }, route: { id: '/lines/[line]' } };",
			'$app/env/public': "export const PUBLIC_DATA_BASE = '/data';"
		};
		if (!(specifier in stubs)) return nextResolve(specifier, context);
		return {
			url: `data:text/javascript,${encodeURIComponent(stubs[specifier])}`,
			shortCircuit: true
		};
	}
});

const DESCRIPTION = 'How late LA Metro buses and trains run, measured against the timetable.';

function parse(head: string) {
	const { document } = parseHTML(`<!doctype html><html><head>${head}</head><body></body></html>`);
	const metas = (attr: 'name' | 'property', key: string) =>
		[...document.querySelectorAll(`meta[${attr}="${key}"]`)].map((el) =>
			el.getAttribute('content')
		);
	return {
		titles: [...document.querySelectorAll('title')].map((el) => el.textContent),
		canonical: [...document.querySelectorAll('link[rel="canonical"]')].map((el) =>
			el.getAttribute('href')
		),
		name: (key: string) => metas('name', key),
		property: (key: string) => metas('property', key)
	};
}

function headOf(props: { title: string; description: string; path: string; noindex?: boolean }) {
	return parse(render(PageHead, { props }).head);
}

test('emits the title, description, canonical, Open Graph and Twitter tags once each', () => {
	const head = headOf({ title: 'Ranking', description: DESCRIPTION, path: '/ranking' });
	assert.deepEqual(head.titles, ['Ranking · HowLate']);
	assert.deepEqual(head.name('description'), [DESCRIPTION]);
	assert.equal(head.canonical.length, 1);
	assert.deepEqual(head.property('og:type'), ['website']);
	assert.deepEqual(head.property('og:site_name'), ['HowLate']);
	assert.deepEqual(head.property('og:title'), ['Ranking · HowLate']);
	assert.deepEqual(head.property('og:description'), [DESCRIPTION]);
	assert.equal(head.property('og:url').length, 1);
	assert.equal(head.property('og:image').length, 1);
	assert.deepEqual(head.name('twitter:card'), ['summary_large_image']);
	assert.deepEqual(head.name('twitter:title'), ['Ranking · HowLate']);
	assert.deepEqual(head.name('twitter:description'), [DESCRIPTION]);
	assert.equal(head.name('twitter:image').length, 1);
});

test('the canonical link and og:url come from SITE_URL and the path', () => {
	const head = headOf({ title: 'Methods', description: DESCRIPTION, path: '/methods' });
	assert.equal(SITE_URL.startsWith('https://'), true);
	assert.equal(SITE_URL.endsWith('/'), false);
	assert.deepEqual(head.canonical, [`${SITE_URL}/methods`]);
	assert.deepEqual(head.property('og:url'), [`${SITE_URL}/methods`]);
	const line = headOf({ title: 'Route 720', description: DESCRIPTION, path: '/lines/720' });
	assert.deepEqual(line.canonical, [`${SITE_URL}/lines/720`]);
});

test('the preview image address is absolute and the same in both card formats', () => {
	const head = headOf({ title: 'Methods', description: DESCRIPTION, path: '/methods' });
	assert.deepEqual(head.property('og:image'), [`${SITE_URL}/og.png`]);
	assert.deepEqual(head.name('twitter:image'), [`${SITE_URL}/og.png`]);
});

test('the home page keeps its whole title, and other pages end in the site name', () => {
	const home = headOf({
		title: 'HowLate · How late is LA Metro?',
		description: DESCRIPTION,
		path: '/'
	});
	assert.deepEqual(home.titles, ['HowLate · How late is LA Metro?']);
	assert.deepEqual(home.canonical, [`${SITE_URL}/`]);
	assert.deepEqual(home.property('og:title'), ['HowLate · How late is LA Metro?']);
});

test('noindex adds the robots tag and nothing else does', () => {
	const props = { title: 'Specimen', description: DESCRIPTION, path: '/design' };
	assert.deepEqual(headOf({ ...props, noindex: true }).name('robots'), ['noindex']);
	assert.deepEqual(headOf(props).name('robots'), []);
	assert.deepEqual(headOf({ ...props, noindex: false }).name('robots'), []);
});

test('a title with a quote or an ampersand is escaped, not broken out of its tag', () => {
	const head = render(PageHead, {
		props: { title: 'A "b" & <c>', description: 'x"y & <z>', path: '/' }
	}).head;
	assert.doesNotMatch(head, /<c>|<z>/);
	assert.deepEqual(parse(head).name('description'), ['x"y & <z>']);
});

// The route pages render their loading state on the server, which is the head
// that a crawler without JavaScript gets. /design is covered by built.test.ts,
// because it imports the stylesheet as text.
const routes = {
	'/': '../src/routes/+page.svelte',
	'/ranking': '../src/routes/ranking/+page.svelte',
	'/methods': '../src/routes/methods/+page.svelte',
	'/lines/720': '../src/routes/lines/[line]/+page.svelte'
};

test('every route page sets one distinct title and one distinct description of 40 to 160 characters', async () => {
	const titles: string[] = [];
	const descriptions: string[] = [];
	for (const [path, file] of Object.entries(routes)) {
		const page = (await import(file)).default;
		const head = parse(render(page).head);
		assert.equal(head.titles.length, 1, `${path} has ${head.titles.length} titles`);
		assert.equal(head.name('description').length, 1, path);
		const [description] = head.name('description');
		assert.ok(
			description!.length >= 40 && description!.length <= 160,
			`${path}: ${description!.length} characters`
		);
		assert.deepEqual(head.canonical, [`${SITE_URL}${path}`], path);
		titles.push(head.titles[0]);
		descriptions.push(description!);
	}
	assert.equal(new Set(titles).size, titles.length, titles.join(' | '));
	assert.equal(new Set(descriptions).size, descriptions.length);
	assert.equal(titles[0], 'HowLate · How late is LA Metro?');
	assert.equal(titles.at(-1), 'Line 720 · HowLate');
	for (const title of titles.slice(1)) assert.ok(title.endsWith(' · HowLate'), title);
});
