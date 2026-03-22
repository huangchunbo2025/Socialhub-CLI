# Storefront User Cases

This document defines the user cases for the three storefront-facing pages that will be turned into real working pages:

- `index.html`
- `skill.html`
- `user.html`

It is intentionally focused on storefront users, not developer publishing flows or admin moderation flows.

## Scope

These three pages serve the public store and the logged-in store user workflow:

- Discover a skill
- Evaluate whether it is safe and useful
- Decide whether to install it through the CLI
- Keep a personal list of skills and toggle local enablement state

They do **not** cover:

- Developer publishing
- Version submission
- Admin review and certificate revocation

## Primary User

### Store User

A store user is someone who comes to the Skills Store to find a useful skill, inspect it, and then install it through the SocialHub CLI.

Typical traits:

- Not necessarily the person who published the skill
- Wants confidence before installation
- Needs clear release, trust, and install information
- May maintain a personal shortlist or working set of skills

## Product Principles

1. The storefront is evaluation-first, not download-first.
2. Installation always happens in the CLI, not by direct package download.
3. Trust, release clarity, and runtime requirements must be visible before install.
4. Logged-in store users need a lightweight personal workspace, not a developer dashboard.
5. The three pages must feel like one continuous workflow:
   - browse
   - inspect
   - act

## Page 1: `index.html`

## Purpose

The homepage is the storefront catalog page. It helps a user discover skills worth evaluating.

## Core Questions It Must Answer

- What is this store for?
- What skills are available now?
- How do I narrow the catalog quickly?
- How do I move from browsing to detailed evaluation?
- How does installation work?

## Primary Use Cases

### UC-INDEX-01 Browse the catalog

As a store user, I want to scan the available skills quickly so that I can decide what is worth opening.

Expected behavior:

- See a clear store hero
- See the number of published skills
- See the catalog immediately below
- View card-level summary information for each skill

### UC-INDEX-02 Search by intent

As a store user, I want to search by skill name, summary, or workflow so that I can find relevant skills fast.

Expected behavior:

- Search field filters the visible catalog
- Results update quickly
- Empty results state is clear and useful

### UC-INDEX-03 Filter by category

As a store user, I want to filter by category so that I can focus on a narrower set of skills.

Expected behavior:

- Category chips are easy to see
- Active category is visually clear
- Category and search can work together

### UC-INDEX-04 Sort the results

As a store user, I want to sort the catalog so that I can choose between popularity, name, or release recency cues.

Expected behavior:

- Sort options are simple and visible
- Sorting changes only result ordering, not filter state

### UC-INDEX-05 Open a detail page

As a store user, I want to move from a catalog card to a full skill detail page so that I can evaluate the skill properly.

Expected behavior:

- Every skill card has a clear path to `skill.html`
- Card click targets are obvious
- The transition from catalog to detail feels natural

### UC-INDEX-06 Learn the CLI install flow

As a store user, I want to understand the installation model before I sign in or open a skill detail page.

Expected behavior:

- CLI entry is visible in the top bar
- A modal explains install prerequisites and commands
- The page makes it clear that install happens in CLI

## Secondary Use Cases

### UC-INDEX-07 Sign in to personal workspace

As a returning store user, I want to sign in so that I can manage my own working set of skills.

Expected behavior:

- Sign-in entry is visible but not more prominent than browsing
- Sign-in sends me to the store-user flow, not a developer flow

## Content Requirements

The homepage must show:

- Store hero
- Search
- Category chips
- Result count
- Catalog cards
- CLI install entry
- Full footer

Each catalog card should show:

- Display name
- Short summary
- Download count
- Latest version
- Status or review cue if available
- Path to the detail page

## Non-Goals

- No developer publishing controls
- No admin controls
- No raw API console behavior

## Acceptance Criteria

- A new user can understand the store within 10 seconds
- A user can search and filter without confusion
- A user can reach a skill detail page in one click from the catalog
- A user can find the CLI install explanation without leaving the page

## Page 2: `skill.html`

## Purpose

The skill detail page is the evaluation page. It helps a user decide whether a specific skill should be installed.

## Core Questions It Must Answer

- What exactly does this skill do?
- Who published it?
- Is it trustworthy enough to consider?
- What are the runtime requirements?
- How do I install it in the CLI?
- Which version am I looking at?

## Primary Use Cases

### UC-SKILL-01 Understand the skill quickly

As a store user, I want to understand the purpose of the skill in the first screen so that I can decide whether to continue reading.

Expected behavior:

- Clear title
- Strong summary
- Core metadata visible near the top

### UC-SKILL-02 Evaluate trust

As a store user, I want trust and review information before install so that I can judge operational risk.

Expected behavior:

- Trust and identity section
- Security review section
- Release snapshot or equivalent metadata

### UC-SKILL-03 Check runtime requirements

As a store user, I want to understand what this skill needs before install so that I do not break my environment.

Expected behavior:

- Runtime requirements are easy to scan
- Environmental assumptions are clearly listed
- Missing prerequisites are obvious

### UC-SKILL-04 Get the CLI install command

As a store user, I want copyable CLI commands so that I can install the skill directly from SocialHub CLI.

Expected behavior:

- Install section is prominent
- Commands are copyable
- Latest and pinned-version install paths are both visible when relevant

### UC-SKILL-05 Review versions

As a store user, I want to inspect version history so that I can choose a stable release or compare updates.

Expected behavior:

- Versions section exists
- Each version shows basic release metadata
- Version-specific install command is visible where useful

### UC-SKILL-06 Review included docs or package content

As a store user, I want to see what documentation or files are included so that I can evaluate maturity and maintainability.

Expected behavior:

- Files and docs section exists
- The section is structured and readable

## Secondary Use Cases

### UC-SKILL-07 Return to catalog

As a store user, I want a clear way back to the catalog so that I can continue comparing skills.

Expected behavior:

- Back-to-catalog link is obvious

### UC-SKILL-08 Open the CLI help modal

As a store user, I want the same CLI explanation available here so that I do not need to return to the homepage.

Expected behavior:

- Same top-right CLI button
- Same modal behavior as other storefront pages

## Content Requirements

The detail page must show:

- Hero identity section
- Install summary or install side card
- Overview
- Trust and identity
- Security review
- Runtime requirements
- Install section
- Files and docs
- Versions
- Full footer

## Non-Goals

- No direct package download as the primary action
- No developer editing controls
- No admin review controls

## Acceptance Criteria

- A user can decide whether to install without opening a second page
- A user can copy a CLI install command in one action
- Trust and runtime information is visible before the install section ends

## Page 3: `user.html`

## Purpose

The user workspace is the logged-in store-user page. It is not a developer dashboard. It helps a user manage their own working set and install workflow.

## Core Questions It Must Answer

- Which skills am I currently tracking or using?
- Which of them are enabled or disabled for me?
- How do I install or re-open details?
- How do I leave the session?

## Primary Use Cases

### UC-USER-01 View my working set

As a store user, I want to see a small list of my relevant skills so that I can continue where I left off.

Expected behavior:

- “My skills” appears as the primary tab
- Skill cards are easy to scan
- Each card links back to the detail page

### UC-USER-02 Toggle skill state

As a store user, I want to manually toggle a skill between enabled and disabled so that I can track my intended usage state.

Expected behavior:

- State is displayed as a button
- Clicking toggles between `Enabled` and `Disabled`
- State persists locally in the browser

Note:

- This is currently a storefront-side user preference, not a backend installation status

### UC-USER-03 Revisit installation guidance

As a store user, I want to re-read the install workflow so that I can follow the approved install path.

Expected behavior:

- “Install workflow” tab explains the evaluation-to-CLI path
- Copy and guidance are concise

### UC-USER-04 Sign out

As a store user, I want to end my session safely so that I can switch accounts or leave the shared machine.

Expected behavior:

- Logout is a dedicated tab
- Sign-out action is explicit

## Secondary Use Cases

### UC-USER-05 Return to store

As a store user, I want to go back to the catalog at any time so that I can keep browsing.

Expected behavior:

- `Back to store` is visible in the top bar

### UC-USER-06 Access CLI help

As a store user, I want the CLI modal available in workspace too so that I can copy commands without leaving the page.

Expected behavior:

- Same top-right CLI button
- Same modal behavior and content

## Content Requirements

The user page must show:

- User identity
- My skills tab
- Install workflow tab
- Logout tab
- Top CLI button
- Full footer

Each skill card should show:

- Name
- Summary
- Local state button
- Latest version
- Download count
- Link to detail page

## Non-Goals

- No developer publishing actions
- No developer profile editing
- No admin metrics or moderation actions

## Acceptance Criteria

- A signed-in store user never lands in the developer dashboard by accident
- The skills list uses user-centric state, not raw category labels as pseudo-status
- A user can toggle state in one click
- A user can open the detail page from every skill card

## Cross-Page Flow

The intended storefront flow is:

1. User arrives on `index.html`
2. User searches or filters the catalog
3. User opens `skill.html`
4. User reviews trust, runtime, and install guidance
5. User signs in if needed
6. User lands in `user.html`
7. User manages personal skill states and returns to details when needed
8. User installs through CLI outside the web page

## Open Implementation Notes

These user cases imply the following upcoming implementation work:

1. `index.html`
   - Real search, filter, sort, and catalog rendering
2. `skill.html`
   - Real detail rendering from backend fields
   - Strong install command handling
3. `user.html`
   - Real store-user session handling
   - Local per-skill state management
   - Clear distinction between local state and backend release state

