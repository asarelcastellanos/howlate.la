/** "2026-11-15" as "November 15, 2026". It reads the day as UTC so no time zone shifts it. */
export function longDate(day: string): string {
	return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-US', {
		month: 'long',
		day: 'numeric',
		year: 'numeric',
		timeZone: 'UTC'
	});
}
