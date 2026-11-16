// Generated from ../../../../pipeline/schemas by scripts/generate-types.mjs.
// Do not edit. Run `npm run types` in web/ to regenerate it, and commit the
// result in the same PR as the schema change.

/**
 * Current run pointer. site/current.json. The one file that moves when a run is published. A reader fetches it first, then reads every other file from the run it names, so it never sees a mix of two runs.
 *
 * @see https://howlate.la/schemas/current.schema.json
 */
export interface CurrentPointer {
	/**
	 * The run's name, which is its UTC start time followed by a random suffix. Names sort by age.
	 */
	run: string;
	/**
	 * Where the run's files are, relative to the bucket root and ending in a slash. Append index.json, status.json or lines/<line>.json.
	 */
	prefix: string;
	/**
	 * How many files the run holds.
	 */
	files: number;
	/**
	 * The runs that were current before this one, newest first. They stay in the bucket so a reader that fetched an older pointer can finish.
	 *
	 * @maxItems 2
	 */
	previous: [] | [string] | [string, string];
}

/**
 * Line index. index.json. One entry per line with headline numbers, so the homepage and line search need no other file. Lines with no measured arrival are left out.
 *
 * @see https://howlate.la/schemas/index.schema.json
 */
export interface SiteIndex {
	/**
	 * The earliest service day in the data, as YYYY-MM-DD.
	 */
	first_day: string;
	/**
	 * The latest service day in the data, as YYYY-MM-DD.
	 */
	last_day: string;
	/**
	 * How many service days have data.
	 */
	days: number;
	/**
	 * Every line, with bus lines before rail lines, and shorter line numbers before longer ones.
	 */
	lines: IndexEntry[];
}
export interface IndexEntry {
	/**
	 * The line id, as in Metro's timetable. It names the line's file, lines/<line>.json.
	 */
	line: string;
	/**
	 * Which Metro feed the line is in. LACMTA is bus and LACMTA_Rail is rail. The same line id could appear in both.
	 */
	agency: 'LACMTA' | 'LACMTA_Rail';
	/**
	 * The name riders use. The route number for a bus, such as 720, and the line name for rail, such as Metro A Line.
	 */
	label: string;
	/**
	 * The corridor the line runs along, in title case. Empty for rail.
	 */
	via: string;
	/**
	 * Bus or rail.
	 */
	mode: 'bus' | 'rail';
	/**
	 * Arrivals with a measured delay, over all days.
	 */
	n: number;
	/**
	 * Scheduled stops over all days, measured or not. Divide n by this for coverage.
	 */
	sched: number;
	/**
	 * Median delay in seconds. Positive means late and negative means early.
	 */
	med: number;
	/**
	 * 90th percentile delay in seconds. One measured arrival in ten was later than this.
	 */
	p90: number;
	/**
	 * Percent of measured arrivals more than 300 seconds late, to one decimal place.
	 */
	pct5: number;
	/**
	 * Where each measured direction is signed for, in direction order. An empty string means the timetable names no destination.
	 *
	 * @minItems 1
	 * @maxItems 2
	 */
	to: [string] | [string, string];
}

/**
 * Line detail. lines/<line>.json. Everything the line page shows, in two grains. The profile pools every stop to answer when the line is worst. The per-stop cells pool six dayparts to answer how bad one stop is. A finer grid would hold too few arrivals per cell to mean anything.
 *
 * @see https://howlate.la/schemas/line.schema.json
 */
export interface LineFile {
	/**
	 * The line id, as in Metro's timetable. The file is named after it.
	 */
	line: string;
	/**
	 * Which Metro feed the line is in. LACMTA is bus and LACMTA_Rail is rail.
	 */
	agency: 'LACMTA' | 'LACMTA_Rail';
	/**
	 * The name riders use. The route number for a bus and the line name for rail.
	 */
	label: string;
	/**
	 * The corridor the line runs along, in title case. Empty for rail.
	 */
	via: string;
	/**
	 * Bus or rail.
	 */
	mode: 'bus' | 'rail';
	/**
	 * The earliest service day in the data, as YYYY-MM-DD. This is network-wide, not specific to the line.
	 */
	first_day: string;
	/**
	 * The latest service day in the data, as YYYY-MM-DD.
	 */
	last_day: string;
	/**
	 * How many service days have data, network-wide.
	 */
	days: number;
	/**
	 * The directions with at least one measured arrival, in direction id order. A direction never observed is absent.
	 *
	 * @minItems 1
	 * @maxItems 2
	 */
	directions: [Direction] | [Direction, Direction];
}
export interface Direction {
	/**
	 * The timetable's direction id, 0 or 1. Use the to field to name the direction for a rider.
	 */
	id: 0 | 1;
	/**
	 * Where this direction is signed for. It is the destination that appears on the most of the direction's timetable stops. Empty when the timetable names none.
	 */
	to: string;
	/**
	 * Arrivals with a measured delay in this direction, summed over its stops.
	 */
	n: number;
	/**
	 * Scheduled stops in this direction, summed over its stops, measured or not.
	 */
	sched: number;
	/**
	 * The hour-of-week shape, pooled over every stop. Hours with nothing measured are left out, so there are up to 168 entries, sorted by h.
	 *
	 * @minItems 1
	 */
	profile: [Hour, ...Hour[]];
	/**
	 * Every stop with a scheduled arrival in this direction, in route order. Stops that are only a trip's first stop are left out, because they measure a departure.
	 *
	 * @minItems 1
	 */
	stops: [Stop, ...Stop[]];
}
export interface Hour {
	/**
	 * Hour of the week in Los Angeles time, from the scheduled time. 0 is Monday 00:00 to 00:59, 24 is Tuesday 00:00, and 167 is Sunday 23:00.
	 */
	h: number;
	/**
	 * Arrivals with a measured delay in this hour, over all days and stops.
	 */
	n: number;
	/**
	 * Scheduled stops in this hour, measured or not.
	 */
	sched: number;
	/**
	 * Median delay in seconds. Positive means late and negative means early.
	 */
	med: number;
	/**
	 * 90th percentile delay in seconds. One measured arrival in ten was later than this.
	 */
	p90: number;
	/**
	 * Percent of measured arrivals more than 300 seconds late, to one decimal place.
	 */
	pct5: number;
}
export interface Stop {
	/**
	 * The stop id, as in Metro's timetable.
	 */
	id: string;
	/**
	 * The stop's name. It falls back to the stop id when the timetable has no name for it.
	 */
	name: string;
	/**
	 * Latitude in degrees. Null when the timetable has no coordinates for the stop.
	 */
	lat: number | null;
	/**
	 * Longitude in degrees. Null when the timetable has no coordinates for the stop.
	 */
	lon: number | null;
	/**
	 * Where the stop sits along the route. It is the median stop sequence over all trips, so sort by it and do not read it as a count of stops.
	 */
	seq: number;
	/**
	 * Arrivals with a measured delay at this stop, over all days. It counts every daypart and can be 0.
	 */
	n: number;
	/**
	 * Scheduled stops here, measured or not. It also counts dayparts missing from cells, so a gap in cells is not a gap in the timetable.
	 */
	sched: number;
	/**
	 * One entry per daypart with at least one measured arrival, sorted by d. Dayparts with none are left out.
	 */
	cells: Cell[];
}
export interface Cell {
	/**
	 * Kind of day, then part of the day, in Los Angeles time from the scheduled time. wk is Monday to Friday, sa is Saturday and su is Sunday. early is 00:00 to 05:59, am is 06:00 to 08:59, mid is 09:00 to 14:59, pm is 15:00 to 18:59, eve is 19:00 to 21:59 and late is 22:00 to 23:59.
	 */
	d: string;
	/**
	 * Arrivals with a measured delay in this daypart, over all days.
	 */
	n: number;
	/**
	 * Scheduled stops in this daypart, measured or not. Compare it with n before trusting med.
	 */
	sched: number;
	/**
	 * Median delay in seconds. Positive means late and negative means early.
	 */
	med: number;
	/**
	 * 90th percentile delay in seconds. One measured arrival in ten was later than this.
	 */
	p90: number;
	/**
	 * Percent of measured arrivals more than 300 seconds late, to one decimal place.
	 */
	pct5: number;
}

/**
 * Network status. status.json. Network-wide totals over every service day collected so far, for the status strip. Trip origins are left out of every count, because they measure a departure and not an arrival.
 *
 * @see https://howlate.la/schemas/status.schema.json
 */
export interface SiteStatus {
	/**
	 * The earliest service day in the data, as YYYY-MM-DD.
	 */
	first_day: string;
	/**
	 * The latest service day in the data, as YYYY-MM-DD. This is the freshness date to show, because the file carries no run time.
	 */
	last_day: string;
	/**
	 * How many service days have data. Days with no data are not counted, so this can be less than the span from first_day to last_day.
	 */
	days: number;
	/**
	 * Scheduled stops over all days, measured or not.
	 */
	scheduled_stops: number;
	/**
	 * Scheduled stops where a vehicle was seen and the delay could be measured.
	 */
	measured_arrivals: number;
	/**
	 * measured_arrivals as a percent of scheduled_stops, to one decimal place.
	 */
	coverage_pct: number;
	/**
	 * Distinct lines in the scheduled stops. This can be larger than the number of lines in index.json, which lists only lines with at least one measured arrival.
	 */
	lines: number;
	/**
	 * Distinct scheduled trip ids over all days.
	 */
	trips: number;
}
