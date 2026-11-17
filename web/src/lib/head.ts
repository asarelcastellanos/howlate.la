import { SITE_URL } from './config.ts';

export const SITE_NAME = 'HowLate';

/** Under this a description says too little to be a search snippet, and over it search results cut it off. */
export const DESCRIPTION_LENGTH = { min: 40, max: 160 } as const;

/** The home page title already holds the site name, so only other pages get it added. */
export function fullTitle(title: string, path: string): string {
	return path === '/' ? title : `${title} · ${SITE_NAME}`;
}

/** The absolute address of a path on the site. Preview cards and canonical links need it absolute. */
export const absoluteUrl = (path: string): string => `${SITE_URL}${path}`;

/** The preview image is a static file, so its address is the same on every page. */
export const OG_IMAGE = absoluteUrl('/og.png');
