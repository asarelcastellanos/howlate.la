/**
 * Whether a rail line page shows its on-time share. It is on since 0.5.1. HowLate
 * scores rail at 64.4 percent while Metro publishes 99.4 percent, and the cause
 * is still not known (issues #133 and #157). The owner decided on 2026-11-18 to
 * publish the share anyway, with a note beside it that says how it is measured
 * and why it differs from Metro's. Turn it off to hold the rail share back again.
 */
export const SHOW_RAIL_ONTIME = true;

/**
 * The address that canonical links and preview cards use. It is the custom
 * domain, which replaced the Cloudflare Pages address in 0.5.0 (issue #32). It
 * has no trailing slash.
 */
export const SITE_URL = 'https://howlate.la';
