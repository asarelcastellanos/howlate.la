/**
 * Plot puts aria-label on each mark group ("cell", "rule", "dot") and on each
 * axis group, none with a role. ARIA forbids a label on a generic element, and
 * axe reports 13 serious aria-prohibited-attr nodes on /lines/720 for them.
 * The groups add nothing a screen reader can use, because the chart's own label
 * states the finding. A group that has a role keeps its label, and so does the
 * svg itself, which this selector never matches.
 */
export function dropGroupLabels(chart: Element): void {
	for (const group of chart.querySelectorAll('g[aria-label]:not([role])')) {
		group.removeAttribute('aria-label');
	}
}
