// Text boxes read off a drawn SVG, for tests that check labels do not collide.
// linkedom has no layout, so the width of a text is its length times a fixed
// pixel width, the same estimate the charts use when they place a label.
export type Box = { text: string; left: number; right: number; top: number; bottom: number };

const CHAR_PX = 7;
const HEIGHT = 14;

const translate = (el: Element) => {
	const m = /translate\((-?[\d.e+-]+)(?:[ ,]+(-?[\d.e+-]+))?\)/.exec(
		el.getAttribute('transform') ?? ''
	);
	return m ? { x: Number(m[1]), y: Number(m[2] ?? 0) } : { x: 0, y: 0 };
};

export function textBoxes(svg: Element): Box[] {
	return [...svg.querySelectorAll('text')].map((el) => {
		let x = 0;
		let y = 0;
		let anchor: string | null = null;
		for (let n: Element | null = el; n && n !== svg.parentElement; n = n.parentElement) {
			const t = translate(n);
			x += t.x;
			y += t.y;
			anchor ??= n.getAttribute('text-anchor');
		}
		const text = el.textContent ?? '';
		const width = text.length * CHAR_PX;
		const left = anchor === 'end' ? x - width : anchor === 'start' ? x : x - width / 2;
		// Plot sets y="0.71em" on text that hangs from its point and "0.32em" on text centered on it.
		const top = el.getAttribute('y') === '0.71em' ? y : y - HEIGHT / 2;
		return { text, left, right: left + width, top, bottom: top + HEIGHT };
	});
}

export const overlap = (a: Box, b: Box) =>
	a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

/** Every pair of boxes that overlap, as readable strings. An empty list means none do. */
export function collisions(boxes: Box[]): string[] {
	const found: string[] = [];
	for (let i = 0; i < boxes.length; i++) {
		for (let j = i + 1; j < boxes.length; j++) {
			if (overlap(boxes[i], boxes[j])) found.push(`"${boxes[i].text}" and "${boxes[j].text}"`);
		}
	}
	return found;
}
