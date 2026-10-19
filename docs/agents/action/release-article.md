# Release Articles

Write the [blog](https://blog.infinito.nexus/) article for a release and its banner image.
The article is one HTML file for a single WordPress Custom HTML block; the banner is a separate PNG for the post's Featured image.

## Inputs

- The release version (for example `16.0`) and its tag. When the `.0` tag was never published, the first published patch tag is the release tag and its upgrade notes count too.
- The release sections of [CHANGELOG.md](../../../CHANGELOG.md).
- The latest article in the Release category of the blog, as the reference for length, tone and structure.

## Output

- You MUST write every file to a work folder outside the repository and MUST NOT commit the article or the banner.
- The work folder holds `article.html`, `banner.svg`, `banner.png` (1500 × 1000) and `post.md` (title, category, tags).

## Procedure

1. Read the release sections of the changelog. Take the headline feature from the operator, otherwise the largest `Added` entry. Read the README of the role behind it so every claim is right.
2. Fetch the reference article and measure its body, from `<div class="inf-release">` to its end: visible text characters (SVG icons excluded), words and markup lines. The new article MUST land within ±5 % on characters and on lines.
3. Copy [templates/article.html](../../../skills/i8-release-article/templates/article.html) and fill it in its order: badge; intro and a second paragraph; the warning (major releases only, otherwise drop the block); three feature cards; one or two sections on the headline feature with a bold-lead list; the callout; an optional "Also New" section; Before You Upgrade; More Reliable (three or four fixes); Updated Applications (about thirteen chips from the version jumps, major versions first); the closing section. Repeat card, list item, table row and chip blocks as needed and remove every `{{…}}` placeholder.
4. Write every sentence to the standard below.
5. Copy [templates/banner.svg](../../../skills/i8-release-article/templates/banner.svg) and fill it: `{{LOGO}}` with the `file://` URL of [assets/img/logo.png](../../../assets/img/logo.png), `{{VERSION}}`, two subtitle lines of at most 34 characters, four `{{ICON_n}}` (24 × 24 outline icons) and four `{{LABEL_n}}` (plain words, at most 14 characters) for the headline feature's benefits.
6. Render the banner with Playwright's headless shell (`~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell`) and the flags `--disable-gpu --hide-scrollbars --allow-file-access-from-files --window-size=1500,1000 --screenshot=<work>/banner.png file://<work>/banner.svg`. Look at the PNG and fix overlaps or cut text before you go on.
7. Verify: no `{{` left; no `<code>`, command, flag, path or variable in the visible text; lengths within range; every number and version matches the changelog. Render the article on a dark page at about 860 px width and look at it.
8. Hand over the paths, the title, the category `Release`, ten to twenty tags, and the WordPress steps: paste the whole `article.html` into one Custom HTML block, set `banner.png` as the Featured image.

## Writing Standard

- Feature-oriented: say what the reader gets and why it matters, not how it is built.
- No commands, flags, file paths, variable names, role names, inventory keys or code, and no `<code>` tags. Product names, application names and version numbers are fine.
- Second person ("your servers"), present tense, short sentences, American English.
- Every claim MUST trace back to the changelog or to the README of the role behind it. No invented numbers, benefits or comparisons. Beta features say "beta".
- Section titles name a benefit ("A Private Network Between Your Servers"); list items open with a bold benefit lead.
- Before You Upgrade keeps every upgrade note of the changelog and phrases the action the reader takes, not the mechanism behind it.

## Rules

- You MUST NOT publish to, or sign in to, the blog. The operator publishes.
- You MUST NOT add the banner to the article HTML; it belongs in the Featured image.
