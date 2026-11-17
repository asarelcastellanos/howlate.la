import type { LineFile, SiteIndex, SiteStatus } from './types';

// A body is JSON, but the live bucket can hold an older shape than the types say.
// It does between a release and the first daily run after it. These checks read
// only the fields a page uses, so a file the page cannot draw becomes an error
// state and not an exception. The pipeline's contract test checks the full shape.
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown) => typeof v === 'number';
const str = (v: unknown) => typeof v === 'string';
const list = (v: unknown, each: (item: unknown) => boolean) => Array.isArray(v) && v.every(each);
const some = (v: unknown, each: (item: unknown) => boolean) =>
	Array.isArray(v) && v.length > 0 && v.every(each);
const mode = (v: unknown) => v === 'bus' || v === 'rail';

const isHour = (v: unknown) =>
	isObj(v) && num(v.h) && num(v.n) && num(v.med) && num(v.p90) && num(v.ontime);

const isCell = (v: unknown) => isObj(v) && str(v.d) && num(v.n) && num(v.med);

// A stop with no measured arrival has null numbers.
const isStop = (v: unknown) =>
	isObj(v) &&
	str(v.name) &&
	num(v.seq) &&
	isObj(v.all) &&
	(v.all.med === null || num(v.all.med)) &&
	list(v.cells, isCell);

const isDirection = (v: unknown) =>
	isObj(v) &&
	str(v.to) &&
	isObj(v.all) &&
	num(v.all.n) &&
	num(v.all.med) &&
	num(v.all.p90) &&
	num(v.all.ontime) &&
	some(v.profile, isHour) &&
	some(v.stops, isStop);

export const isLineFile = (v: unknown): v is LineFile =>
	isObj(v) &&
	str(v.label) &&
	str(v.via) &&
	mode(v.mode) &&
	str(v.last_day) &&
	num(v.days) &&
	some(v.directions, isDirection);

const isEntry = (v: unknown) =>
	isObj(v) &&
	str(v.line) &&
	str(v.label) &&
	str(v.via) &&
	str(v.agency) &&
	mode(v.mode) &&
	list(v.to, str);

export const isSiteIndex = (v: unknown): v is SiteIndex => isObj(v) && list(v.lines, isEntry);

export const isSiteStatus = (v: unknown): v is SiteStatus =>
	isObj(v) && str(v.last_day) && num(v.days) && num(v.measured_arrivals) && num(v.coverage_pct);
