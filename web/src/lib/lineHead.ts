import type { IndexEntry, LineFile } from './data/types';
import { DESCRIPTION_LENGTH } from './head.ts';

/** What a line page's head needs from the index, and nothing that changes day to day. */
export type LineListEntry = Pick<IndexEntry, 'line' | 'label' | 'mode' | 'via'> & {
	to: readonly string[];
};

/** The committed list keeps these fields only, so no metric or rail figure is ever in git. */
export function toListEntry(entry: IndexEntry): LineListEntry {
	const { line, label, mode, to, via } = entry;
	return { line, label, mode, to, via };
}

/**
 * The same five fields from a loaded line file, for a line the committed list lacks.
 * A direction's `to` is the destination its timetable stops sign, so the two read like the index's.
 */
export function listEntryOfFile(
	file: Pick<LineFile, 'line' | 'label' | 'mode' | 'via' | 'directions'>
): LineListEntry {
	const { line, label, mode, via } = file;
	return { line, label, mode, to: file.directions.map((d) => d.to).filter(Boolean), via };
}

/** Checks the committed list, which the build reads and `lines:refresh` writes. */
export function isLineList(value: unknown): value is LineListEntry[] {
	return (
		Array.isArray(value) &&
		value.every(
			(entry) =>
				typeof entry === 'object' &&
				entry !== null &&
				typeof entry.line === 'string' &&
				typeof entry.label === 'string' &&
				(entry.mode === 'bus' || entry.mode === 'rail') &&
				Array.isArray(entry.to) &&
				entry.to.every((name: unknown) => typeof name === 'string') &&
				typeof entry.via === 'string'
		)
	);
}

export const findListed = (list: readonly LineListEntry[], id: string): LineListEntry | undefined =>
	list.find((entry) => entry.line === id);

/** The description for a line the list does not have. */
export const GENERIC_LINE_DESCRIPTION =
	'How late this LA Metro line runs by hour of the week and by stop, measured against the timetable.';

const SUFFIX = ': how late it runs by hour of the week and by stop, against the timetable.';

/** A bus label that is a number or a pair such as 10/48 becomes "Line 10/48". Other labels are names already. */
function lineTitle(entry: LineListEntry): string {
	return entry.mode === 'bus' && /^[\d/]+$/.test(entry.label) ? `Line ${entry.label}` : entry.label;
}

/**
 * The title and description for a line page. The description is the line's name, a
 * short note on where it goes, and one fixed sentence about what the page shows, so
 * no two lines share one (built.test.ts fails the build when two pages do).
 *
 * The note tries the longest form first and takes the first that fits in
 * DESCRIPTION_LENGTH.max: both ends and the corridor, both ends, the first end, then
 * the mode alone. Nothing is cut mid-text, so a note never ends on half a name.
 * In the 2026-11-17 index (115 lines) both ends fit for 99 lines and the first end
 * for 16. The first rung, with the corridor, fits none, because the corridor text
 * of the 109 bus lines that have one is 12 to 483 characters. Descriptions are 120 to 160 characters.
 */
export function lineHead(
	entry: LineListEntry | undefined,
	id: string
): { title: string; description: string } {
	if (!entry) return { title: `Line ${id}`, description: GENERIC_LINE_DESCRIPTION };
	const name = lineTitle(entry).replace(/\s+/g, ' ').trim();
	const kind = entry.mode === 'rail' ? 'rail line' : 'bus line';
	const ends = entry.to.map((end) => end.replace(/\s+/g, ' ').trim()).filter(Boolean);
	const via = entry.via.replace(/\s+/g, ' ').trim();
	const notes = [
		ends.length > 0 && via ? `${kind} to ${ends.join(' and ')}, ${via}` : '',
		ends.length > 0 ? `${kind} to ${ends.join(' and ')}` : '',
		ends.length > 1 ? `${kind} to ${ends[0]}` : '',
		kind
	];
	const describe = (note: string) => `${name} (${note})${SUFFIX}`;
	const note = notes.find(
		(candidate) => candidate !== '' && describe(candidate).length <= DESCRIPTION_LENGTH.max
	);
	if (note) return { title: name, description: describe(note) };

	// A shuttle's label can be a whole sentence. Cut it at a word so the rest still fits.
	const tail = ` (${kind})${SUFFIX}`;
	const cut = name.slice(0, DESCRIPTION_LENGTH.max - tail.length - 1);
	const words = cut.slice(0, cut.lastIndexOf(' ')).trimEnd();
	return { title: name, description: `${words || cut.trimEnd()}…${tail}` };
}
