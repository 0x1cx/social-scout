# TikTok, Instagram, X: read them through Claude in Chrome

These sites have no logged-out read API, so social-scout does not cover them. Scraping them from a script would
mean faking a browser or evading bot detection, which we don't do. Instead, a session reads them in the user's own
Brave through **Claude in Chrome** (`mcp__claude-in-chrome__*`), read-only. The user has approved this for social research.

## Rules
- Read only: never like, follow, comment, post, DM, accept cookie walls beyond "reject non-essential", or log in.
- Stop at login walls, CAPTCHAs or "verify you're human" pages. Note "blocked" in the research file and move on.
- Open a new tab; leave the user's tabs alone. Close your tab when done.
- Quote briefly (one short line per comment), give the URL and the date read, and treat counts as "as displayed".

## How
1. Load the tools in one call:
   `ToolSearch select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__tabs_close_mcp`
2. `tabs_create_mcp`, then `navigate` to a search URL:
   - TikTok: `https://www.tiktok.com/search?q=99%20nights%20in%20the%20forest` (video pages: `https://www.tiktok.com/@user/video/<id>`)
   - Instagram: `https://www.instagram.com/explore/tags/99nightsintheforest/` (often needs login: then skip)
   - X: `https://x.com/search?q=%2299%20nights%20in%20the%20forest%22&f=top` (needs login: skip unless Brave is already signed in)
3. Read with `get_page_text` (cheap) before screenshots. Scroll with `computer` scroll only as far as needed.
4. For a video's comments, open the video page and read the comment panel text. Write down: author, likes as shown, text, URL.
5. Prefer YouTube (`social-scout youtube comments`) for the same creators: many TikTok creators repost there with open comments.
