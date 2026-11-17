# Social preview image

`static/og.png` is the 1200 by 630 image that link previews show. It comes from `scripts/og.html`, which loads the site's fonts from `node_modules`, so run `npm ci` first. Playwright blocks `file:` addresses, so a local server hands it the page.

1. In `web/`, run `python3 -m http.server 4195 --bind 127.0.0.1`, then `playwright-cli -s=og open http://127.0.0.1:4195/scripts/og.html` and `playwright-cli -s=og resize 1200 630`.
2. Run `playwright-cli -s=og screenshot --filename=static/og.png`, then `playwright-cli -s=og close` and stop the server.
3. Check that the file is under 150 KB (it is about 60 KB). If it is larger, run `magick static/og.png -colors 64 PNG8:static/og.png`. `tests/built.test.ts` checks the size and the dimensions.
