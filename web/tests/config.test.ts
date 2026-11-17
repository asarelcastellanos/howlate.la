// The two public addresses. A trailing slash on either would double up when a
// path is added.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULT_DATA_BASE } from '../src/env.ts';
import { SITE_URL } from '../src/lib/config.ts';

test('the default data base is the custom data domain, with no trailing slash', () => {
	assert.equal(DEFAULT_DATA_BASE, 'https://data.howlate.la');
});

test('the site address is the custom domain, with no trailing slash', () => {
	assert.equal(SITE_URL, 'https://howlate.la');
});
