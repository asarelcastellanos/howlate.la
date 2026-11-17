// The service table and the bullet label it feeds. Only the nine lines in the
// table get a service word. Any other line is "Route N".
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { render } from 'svelte/server';
import LineBullet from '../src/lib/design/LineBullet.svelte';
import { serviceOf } from '../src/lib/design/service.ts';
import { bulletProps } from '../src/lib/linePage.ts';

const label = (html: string) => /aria-label="([^"]*)"/.exec(html)![1];

test('each of the nine lines in the table gets its service', () => {
	const expected = {
		'720': 'rapid',
		'754': 'rapid',
		'761': 'rapid',
		'460': 'express',
		'487': 'express',
		'501': 'express',
		'550': 'express',
		'577': 'express',
		'344': 'limited'
	};
	for (const [id, service] of Object.entries(expected)) assert.equal(serviceOf(id), service, id);
	assert.equal(Object.keys(expected).length, 9);
});

test('an id that is not in the table gets no service word', () => {
	// 700, 799, 350 and 450 sit in the number ranges of the nine, and a future
	// line would too. A range must never decide a line's service.
	for (const id of [
		'4',
		'70',
		'700',
		'799',
		'350',
		'450',
		'697',
		'901',
		'720x',
		' 720',
		'',
		'__proto__',
		'constructor'
	]) {
		assert.equal(serviceOf(id), undefined, `"${id}"`);
	}
});

test('the bullet says "Route N" with no service word unless the table names one', () => {
	const bullet = (line: string, route = line) =>
		label(render(LineBullet, { props: bulletProps({ line, label: route, mode: 'bus' }) }).body);
	assert.equal(bullet('4'), 'Route 4');
	assert.equal(bullet('799'), 'Route 799');
	assert.equal(bullet('720'), 'Rapid route 720');
	assert.equal(bullet('344'), 'Limited route 344');
	assert.equal(bullet('487', '487/489'), 'Express route 487/489');
});
