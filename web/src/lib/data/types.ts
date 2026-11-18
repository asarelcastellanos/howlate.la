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
	 * Where the run's files are, relative to the bucket root and ending in a slash. Append index.json, status.json, network.json or lines/<line>.json.
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
 * Pipeline health. health.json. How the daily grading did on the most recent days, for the behind-the-scenes page. It is built from the reports the pipeline saves for each service day. recent is empty when the run had no reports, as in a local run, and then checks is empty too. A day with no report is left out of recent, not marked as failed.
 *
 * @see https://howlate.la/schemas/health.schema.json
 */
export interface HealthFile {
	/**
	 * The version of the pipeline that built this site, such as 0.4.1.
	 */
	pipeline_version: string;
	/**
	 * The newest graded service day, as YYYY-MM-DD. It is the same value as last_day in status.json. Compare it with today's date in Los Angeles to show whether the data is fresh.
	 */
	last_day: string;
	/**
	 * How many service days are graded, which is days in status.json. Every graded day has a saved report. recent lists only the newest 14.
	 */
	days: number;
	/**
	 * The newest service days that have a report, up to 14, newest first. A day with no report is not in the list, so consecutive entries can be more than one day apart.
	 *
	 * @maxItems 14
	 */
	recent: HealthDay[];
	/**
	 * The checks that the report for `last_day` holds, in the order the pipeline runs them, with the pipeline's own plain-words label for each. An empty list when no readable report exists for `last_day`. Reports from older pipeline versions use older names and labels, so list the checks from this field and do not hard-code them.
	 */
	checks: (RangeCheck | CountCheck)[];
}
/**
 * One service day's result.
 */
export interface HealthDay {
	/**
	 * The service day, as YYYY-MM-DD, in Los Angeles time.
	 */
	service_date: string;
	/**
	 * True when every check passed for this day. A day that failed a check is still published, so ok false is a flag for the reader and not a missing day.
	 */
	ok: boolean;
	/**
	 * The names of the checks that failed, in the order the pipeline runs them. Empty when ok is true. Days graded by older pipeline versions can carry names that checks does not list, such as join_rate, which became matched_rate.
	 */
	failed: string[];
	/**
	 * Percent of the day's scheduled stops where a vehicle was seen and the delay measured, to one decimal place. It leaves out the stops in estimated_pct.
	 */
	coverage_pct: number;
	/**
	 * Percent of the day's scheduled stops that the feed never reported and the pipeline placed between two position reports of the same bus, to one decimal place. These have a delay but were not measured. 0 on days graded before the pipeline estimated them.
	 */
	estimated_pct: number;
	/**
	 * Trips that vehicles reported but that have no scheduled stops to grade against, because the timetable lists them only under a service that is not running that day. 0 on days graded before the pipeline counted them.
	 */
	explained_trips: number;
	/**
	 * Percent of the day's vehicle observations that were on those trips, to one decimal place. 0 on days graded before the pipeline counted them.
	 */
	explained_pct: number;
	/**
	 * Stops that vehicles reported on, counted once per trip and stop, whether or not the stop matches the timetable. This can be more than the stops measured.
	 */
	observations: number;
}
/**
 * A check that passes when a measured percentage or value falls between low and high, both included.
 */
export interface RangeCheck {
	/**
	 * The check's short name, which is what failed in a day lists.
	 */
	name: string;
	/**
	 * Tells this shape from a count check.
	 */
	kind: 'range';
	/**
	 * What the check measures, in plain words. The unit is a percent unless the label says otherwise, as in median delay in minutes.
	 */
	label: string;
	/**
	 * True when value is from low to high.
	 */
	ok: boolean;
	/**
	 * What the newest day measured. It has many decimal places, so round it before showing it.
	 */
	value: number;
	/**
	 * The lowest value that passes.
	 */
	low: number;
	/**
	 * The highest value that passes.
	 */
	high: number;
}
/**
 * A check that passes when a count equals the number expected.
 */
export interface CountCheck {
	/**
	 * The check's short name, which is what failed in a day lists.
	 */
	name: string;
	/**
	 * Tells this shape from a range check.
	 */
	kind: 'count';
	/**
	 * What is counted, in plain words.
	 */
	label: string;
	/**
	 * True when value equals expected.
	 */
	ok: boolean;
	/**
	 * The count the newest day measured.
	 */
	value: number;
	/**
	 * The count that passes.
	 */
	expected: number;
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
	 * Of n, the arrivals placed between two position reports of the same bus because the feed never reported this stop (source interpolated in the arrivals table). The rest were seen at the stop or timed from an approach report. The estimate is in n, the median and the on-time share like any other arrival.
	 */
	est: number;
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
	 * Percent of measured arrivals from 60 seconds early to 300 seconds late, both included, to one decimal place. HowLate scores the arrival at every scheduled stop. Metro scores timepoints and rail terminals only, so this is not Metro's published on-time performance.
	 */
	ontime: number;
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
	all: Delays;
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
/**
 * The delay numbers over every measured arrival in one direction, on every day and hour. n equals the direction's n.
 */
export interface Delays {
	/**
	 * Arrivals with a measured delay.
	 */
	n: number;
	/**
	 * Of n, the arrivals placed between two position reports of the same bus because the feed never reported this stop (source interpolated in the arrivals table). The rest were seen at the stop or timed from an approach report. The estimate is in n, the median and the on-time share like any other arrival.
	 */
	est: number;
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
	 * Percent of measured arrivals from 60 seconds early to 300 seconds late, both included, to one decimal place. HowLate scores the arrival at every scheduled stop. Metro scores timepoints and rail terminals only, so this is not Metro's published on-time performance.
	 */
	ontime: number;
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
	/**
	 * Percent of measured arrivals from 60 seconds early to 300 seconds late, both included, to one decimal place. HowLate scores the arrival at every scheduled stop. Metro scores timepoints and rail terminals only, so this is not Metro's published on-time performance.
	 */
	ontime: number;
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
	 * Of n, the arrivals placed between two position reports of the same bus because the feed never reported this stop (source interpolated in the arrivals table). The rest were seen at the stop or timed from an approach report. The estimate is in n, the median and the on-time share like any other arrival.
	 */
	est: number;
	/**
	 * Scheduled stops here, measured or not. It also counts dayparts missing from cells, so a gap in cells is not a gap in the timetable.
	 */
	sched: number;
	all: StopDelays;
	/**
	 * One entry per daypart with at least one measured arrival, sorted by d. Dayparts with none are left out.
	 */
	cells: Cell[];
}
/**
 * The delay numbers over every measured arrival at one stop, on every day and hour. The cells split the same arrivals by daypart and leave out dayparts with none, so use this for one number per stop. The count is the stop's n.
 */
export interface StopDelays {
	/**
	 * Median delay in seconds. Positive means late and negative means early. Null when the stop's n is 0.
	 */
	med: number | null;
	/**
	 * 90th percentile delay in seconds. One measured arrival in ten was later than this. Null when the stop's n is 0.
	 */
	p90: number | null;
	/**
	 * Percent of measured arrivals more than 300 seconds late, to one decimal place. Null when the stop's n is 0.
	 */
	pct5: number | null;
	/**
	 * Percent of measured arrivals from 60 seconds early to 300 seconds late, both included, to one decimal place. Null when the stop's n is 0. HowLate scores the arrival at every scheduled stop. Metro scores timepoints and rail terminals only, so this is not Metro's published on-time performance.
	 */
	ontime: number | null;
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
 * Network profile. network.json. The whole network's delay numbers and hour-of-week shape, for the network as a whole and for bus and rail alone. network holds every line, bus holds the lines that index.json gives the mode bus, and rail holds the lines with the mode rail. The hour profile pools every line and stop, so it cannot be built from the line files. Trip origins are left out of every count, because they measure a departure and not an arrival.
 *
 * @see https://howlate.la/schemas/network.schema.json
 */
export interface NetworkFile {
	network: NetworkScope;
	bus: NetworkScope;
	rail: NetworkScope;
}
/**
 * The delay numbers and hour-of-week shape for one part of the network. A mode with no measured arrival is still present, with an n of 0 and an empty profile.
 */
export interface NetworkScope {
	all: NetworkDelays;
	/**
	 * The hour-of-week shape, pooled over every line and stop in this scope. Hours with nothing measured are left out, so there are up to 168 entries, sorted by h. The array is empty when nothing was measured.
	 *
	 * @maxItems 168
	 */
	profile: NetworkHour[];
}
/**
 * The delay numbers over every measured arrival in this scope, on every day and hour.
 */
export interface NetworkDelays {
	/**
	 * Arrivals with a measured delay. It is 0 when nothing was measured in this scope, and then every other field is null.
	 */
	n: number;
	/**
	 * Of n, the arrivals placed between two position reports of the same bus because the feed never reported this stop (source interpolated in the arrivals table). The rest were seen at the stop or timed from an approach report. The estimate is in n, the median and the on-time share like any other arrival. It is 0 when n is 0, and 0 for rail, which is never estimated this way.
	 */
	est: number;
	/**
	 * Median delay in seconds. Positive means late and negative means early. Null when n is 0.
	 */
	med: number | null;
	/**
	 * 90th percentile delay in seconds. One measured arrival in ten was later than this. Null when n is 0.
	 */
	p90: number | null;
	/**
	 * Percent of measured arrivals more than 300 seconds late, to one decimal place. Null when n is 0.
	 */
	pct5: number | null;
	/**
	 * Percent of measured arrivals from 60 seconds early to 300 seconds late, both included, to one decimal place. Null when n is 0. HowLate scores the arrival at every scheduled stop. Metro scores timepoints and rail terminals only, so this is not Metro's published on-time performance.
	 */
	ontime: number | null;
}
export interface NetworkHour {
	/**
	 * Hour of the week in Los Angeles time, from the scheduled time. 0 is Monday 00:00 to 00:59, 24 is Tuesday 00:00, and 167 is Sunday 23:00.
	 */
	h: number;
	/**
	 * Arrivals with a measured delay in this hour, over all days, lines and stops.
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
	/**
	 * Percent of measured arrivals from 60 seconds early to 300 seconds late, both included, to one decimal place. HowLate scores the arrival at every scheduled stop. Metro scores timepoints and rail terminals only, so this is not Metro's published on-time performance.
	 */
	ontime: number;
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
	 * Of measured_arrivals, the stops placed between two position reports of the same bus because the feed never reported them. The rest were seen at the stop or timed from an approach report.
	 */
	estimated_arrivals: number;
	/**
	 * measured_arrivals as a percent of scheduled_stops, to one decimal place. It includes estimated_arrivals.
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
