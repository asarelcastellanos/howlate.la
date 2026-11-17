/**
 * An on-time share to one decimal, such as "85.3". A share of 99.95 or more
 * rounds to 100.0, which would say every arrival was on time, so only exactly
 * 100 prints as 100.0 and anything below it stops at 99.9. The heatmap readout
 * keeps the same rule in whole numbers.
 */
export function shareText(value: number): string {
	const text = value.toFixed(1);
	return value < 100 && text === '100.0' ? '99.9' : text;
}
