# To Claude Code

## Context

This repo now contains a completed static prototype for the Skills Store under `skills_store_web/`.

The work was done as a front-end prototype only:
- no backend implementation
- no real auth
- no real API requests
- no changes required in `socialhub/`

## What Was Completed

### 1. Static site build-out

The following prototype pages were created and linked together:

- `skills_store_web/index.html`
- `skills_store_web/installed.html`
- `skills_store_web/login.html`
- `skills_store_web/register.html`
- `skills_store_web/account-profile.html`
- `skills_store_web/logout.html`
- `skills_store_web/developer-portal.html`
- `skills_store_web/developer-skills.html`
- `skills_store_web/developer-submit.html`
- `skills_store_web/developer-settings.html`
- `skills_store_web/admin-portal.html`
- `skills_store_web/admin-certificates.html`
- `skills_store_web/admin-catalog.html`
- `skills_store_web/admin-stats.html`

Shared assets:

- `skills_store_web/styles.css`
- `skills_store_web/app.js`
- `skills_store_web/logo.png`

Design rules were documented in:

- `skills_store_web/DESIGN-LANGUAGE.md`

### 2. Design alignment

The developer and admin pages were revised to align with the design language of `index.html`.

Key intent:
- keep a consistent visual language across store, developer, admin, and account pages
- keep footer menus consistent on every page
- keep page content aligned with each page's purpose and filename

### 3. Static account flows

The following flows were prototyped as static pages:

- login
- registration
- profile editing
- logout confirmation

These are UI-only flows. They do not submit to a backend.

### 4. Git / deployment state

Local commits created in the main repo:

- `d458cdb` - `Add complete Skills Store web prototype`
- `52d09e4` - `Add GitHub Pages deployment for skills_store_web`

Important deployment note:

- The workflow commit `52d09e4` exists locally in `main`, but pushing workflow files to GitHub failed due to missing `workflow` scope on the current auth/token.
- As a workaround, the static site was published to the remote `gh-pages` branch from a separate temporary publish repo.

Expected GitHub Pages URL:

- `https://huangchunbo2025.github.io/Socialhub-CLI/`

For Pages to work, the GitHub repo should be configured to serve from:

- Branch: `gh-pages`
- Folder: `/(root)`

## What Claude Code Should Test

### 1. Navigation integrity

Check that all top nav, side nav, CTA buttons, and footer links resolve correctly.

Focus on:
- store pages linking to account, developer, and admin pages
- developer side menu linking to the correct developer pages
- admin side menu linking to the correct admin pages
- footer menu consistency across all pages

### 2. Page-content consistency

Verify each page's default visible content matches its filename and menu state.

Examples:
- `developer-submit.html` should open on the submit workflow, not the overview
- `developer-skills.html` should default to the skills management state
- `admin-certificates.html` should default to certificate management
- `admin-stats.html` should default to statistics/reporting

### 3. Static interaction behavior

Review the demo-only interactions in the JS:
- tab switching
- drawer/modal toggles
- sidebar state switching
- success/confirm dialogs

Check for broken selectors or logic that assumes a page-specific DOM element exists on all pages.

### 4. Layout quality

Manually inspect:
- desktop layout alignment
- common viewport widths
- card spacing
- hero/workspace transitions
- footer spacing and consistency

Primary risk area:
- pages cloned from a template but driven by filename-specific JS state

## What Claude Code Should Review Carefully

### 1. `app.js` assumptions

This prototype relies on static-page behavior and filename-based defaults in some page families.

Review for:
- hard-coded filename mapping
- handlers bound globally that may fail on pages without matching DOM
- duplicated interaction logic between page families

### 2. Template-derived pages

Some pages were produced by adapting a common template and then relying on the current filename to select the active section.

Review for:
- wrong active nav state
- incorrect page title/subtitle
- hidden sections accidentally left visible
- repeated content that no longer matches page purpose

### 3. Footer consistency

This was explicitly requested by the user. Every page should keep the same information architecture in the footer.

Review for:
- missing links
- mismatched labels
- pages that drifted from the shared footer pattern

### 4. Deployment assumptions

The live Pages deployment is branch-based, not Actions-based.

Review for:
- whether `gh-pages` contains the full static site at repo root
- whether the repo Pages setting points to `gh-pages`
- whether the local workflow commit should eventually be pushed using a token with `workflow` scope, or dropped if branch-based Pages is the chosen long-term setup

## Known Non-Goals

These were not implemented:

- backend auth
- registration/login persistence
- API integration
- form validation beyond static/demo behavior
- role-based access control
- production-ready state management

## Recommendation for Next Step

If continuing this work, the best next step is:

1. Do a browser-based QA pass across every page.
2. Fix any mismatched content or broken links.
3. Decide whether the long-term deployment model should stay branch-based (`gh-pages`) or move back to GitHub Actions.
4. Only after that, start converting the prototype into real frontend/backend integration work.
