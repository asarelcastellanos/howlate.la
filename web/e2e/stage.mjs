// Puts the fixture where `vite preview` serves /data from. Preview serves
// .svelte-kit/output/client and not build/, so a copy in build/data is never served.
import { cpSync, mkdirSync, rmSync } from 'node:fs';

const target = new URL('../.svelte-kit/output/client/data/', import.meta.url);
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(new URL('./fixture/site/', import.meta.url), new URL('site/', target), { recursive: true });
console.log('Staged e2e/fixture/site in', target.pathname);
