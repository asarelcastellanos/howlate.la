/**
 * Whether a rail line page shows its on-time share. It is off because HowLate
 * scores rail at 64.4 percent while Metro publishes 99.4 percent, and the cause
 * is not known yet (issue #133). Turn it on only after that issue records the
 * cause and the methodology page says what the rail number means.
 */
export const SHOW_RAIL_ONTIME = false;

/**
 * The address that canonical links and preview cards use. It is the custom
 * domain, which replaced the Cloudflare Pages address in 0.5.1 (issue #32). It
 * has no trailing slash.
 */
export const SITE_URL = 'https://howlate.la';
