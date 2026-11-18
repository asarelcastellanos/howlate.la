/**
 * An on-time share to one decimal, such as "85.3". An unrounded share of 99.95
 * or more would round to 100.0 and say every arrival was on time, so a value
 * below 100 stops at 99.9. This guards unrounded input only. The pipeline already
 * rounds the share to one decimal and the published files carry no on-time count,
 * so a true 99.96 arrives as 100.0 and prints as "100.0". The site cannot tell
 * the two apart. The heatmap readout keeps the same rule in whole numbers.
 */
export function shareText(value: number): string {
	const text = value.toFixed(1);
	return value < 100 && text === '100.0' ? '99.9' : text;
}
