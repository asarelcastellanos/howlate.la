import type { BusService } from './lines.ts';

// The source is Metro's bus timetable file (gtfs_bus 2026-10-12, routes.txt long
// names). These nine lines are the ones it names Rapid, Express or Limited. Every
// other line has no service word and shows as "Route N". The route number does
// not decide it, so a new line in the same range stays neutral until someone
// adds it here from a new timetable.
const SERVICES = new Map<string, Exclude<BusService, 'local'>>([
	['720', 'rapid'],
	['754', 'rapid'],
	['761', 'rapid'],
	['460', 'express'],
	['487', 'express'],
	['501', 'express'],
	['550', 'express'],
	['577', 'express'],
	['344', 'limited']
]);

/** The service of a bus line id as in index.json, or undefined for any line not in the table. */
export const serviceOf = (id: string) => SERVICES.get(id);
