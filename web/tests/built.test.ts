// Reads the prerendered files in build/, so it runs after `vite build` (the
// `postbuild` script) and fails when build/ is missing. 200.html is the client
// shell that serves paths the build did not render, and it has no content.
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, test } from 'node:test';
import { parseHTML } from 'linkedom';

const BUILD = new URL('../build', import.meta.url).pathname;
const SITE_URL = (await import('../src/lib/config.ts')).SITE_URL;
const REQUIRED = [
	'index.html',
	'ranking.html',
	'methods.html',
	'behind-the-scenes.html',
	'design.html'
];

assert.ok(existsSync(BUILD), 'build/ is missing. Run `npm run build`, which runs this test.');

function htmlFiles(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) return entry.name === '_app' ? [] : htmlFiles(path);
		return entry.name.endsWith('.html') && entry.name !== '200.html' ? [path] : [];
	});
}

const files = htmlFiles(BUILD).map((path) => relative(BUILD, path));
const pages = files.map((file) => {
	const { document } = parseHTML(readFileSync(join(BUILD, file), 'utf8'));
	const content = (selector: string) =>
		[...document.querySelectorAll(selector)].map((el) => el.getAttribute('content'));
	const route = '/' + file.replace(/(^|\/)index\.html$/, '').replace(/\.html$/, '');
	return {
		file,
		route,
		document,
		// An inline SVG can carry its own <title>, so only the head's counts.
		title: [...document.querySelectorAll('head > title')].map((el) => el.textContent),
		description: content('meta[name="description"]'),
		meta: content
	};
});

test('the build has every page the site links to', () => {
	for (const file of REQUIRED) assert.ok(files.includes(file), `${file} was not prerendered`);
});

describe('each prerendered page', () => {
	for (const page of pages) {
		test(page.file, () => {
			assert.equal(page.document.querySelectorAll('h1').length, 1, 'h1 count');
			assert.equal(page.title.length, 1, 'title count');
			assert.ok(page.title[0].trim().length > 0, 'empty title');
			assert.equal(page.description.length, 1, 'description count');
			const length = page.description[0]!.length;
			assert.ok(length >= 40 && length <= 160, `description is ${length} characters`);

			const url = `${SITE_URL}${page.route}`;
			assert.deepEqual(
				[...page.document.querySelectorAll('link[rel="canonical"]')].map((el) =>
					el.getAttribute('href')
				),
				[url]
			);
			assert.deepEqual(page.meta('meta[property="og:type"]'), ['website']);
			assert.deepEqual(page.meta('meta[property="og:site_name"]'), ['HowLate']);
			assert.deepEqual(page.meta('meta[property="og:title"]'), page.title);
			assert.deepEqual(page.meta('meta[property="og:description"]'), page.description);
			assert.deepEqual(page.meta('meta[property="og:url"]'), [url]);
			assert.deepEqual(page.meta('meta[property="og:image"]'), [`${SITE_URL}/og.png`]);
			assert.deepEqual(page.meta('meta[name="twitter:card"]'), ['summary_large_image']);
			assert.deepEqual(page.meta('meta[name="twitter:title"]'), page.title);
			assert.deepEqual(page.meta('meta[name="twitter:description"]'), page.description);
			assert.deepEqual(page.meta('meta[name="twitter:image"]'), [`${SITE_URL}/og.png`]);

			const navs = page.document.querySelectorAll('nav[aria-label="Main"]');
			assert.equal(navs.length, 1, 'main nav count');
			assert.ok(navs[0].querySelectorAll('a').length >= 3, 'nav links');
			assert.equal(
				navs[0].querySelectorAll('a[aria-current="page"]').length <= 1,
				true,
				'at most one current link'
			);
			const robots = page.meta('meta[name="robots"]');
			assert.deepEqual(robots, page.file === 'design.html' ? ['noindex'] : []);
		});
	}
});

test('no two pages share a title or a description', () => {
	const titles = pages.map((page) => page.title[0]);
	const descriptions = pages.map((page) => page.description[0]);
	assert.equal(new Set(titles).size, titles.length, titles.join(' | '));
	assert.equal(new Set(descriptions).size, descriptions.length, descriptions.join(' | '));
});

test('the current page is marked in the nav, and the home page title is whole', () => {
	const current = (file: string) =>
		pages
			.find((page) => page.file === file)!
			.document.querySelectorAll('nav[aria-label="Main"] a[aria-current="page"]');
	for (const file of ['ranking.html', 'methods.html', 'behind-the-scenes.html']) {
		const marked = current(file);
		assert.equal(marked.length, 1, file);
		assert.ok(marked[0].getAttribute('href')!.endsWith(file.replace('.html', '')), file);
	}
	assert.equal(current('index.html').length, 1);
	assert.equal(
		pages.find((p) => p.file === 'index.html')!.title[0],
		'HowLate · How late is LA Metro?'
	);
});

test('the preview image is a 1200 by 630 PNG under 150 KB', () => {
	const path = join(BUILD, 'og.png');
	assert.ok(existsSync(path), 'og.png is missing from the build');
	const bytes = readFileSync(path);
	assert.equal(bytes.subarray(1, 4).toString('latin1'), 'PNG');
	assert.equal(bytes.readUInt32BE(16), 1200);
	assert.equal(bytes.readUInt32BE(20), 630);
	assert.ok(statSync(path).size < 150 * 1024, `${statSync(path).size} bytes`);
});
