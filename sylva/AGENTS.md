# PLAY ORBIT — Current project instructions

## Design authority and delivery scope

- The current user-approved authority is `../DESIGN.md` v2.1: fresh white backgrounds with sage greens, chrome typography/material and a yellow #FFC600 belief strip. Older black/neon Acid styling is historical.
- Deliver a desktop Web website only. Do not add a phone app or phone-specific bottom navigation. Focus acceptance on 1024 / 1280 / 1440 / 1920px desktop browser windows. Existing narrow-window fallback CSS can remain for compatibility, not as a separate mobile deliverable.
- Use white page/header/hero surfaces, fresh sage colors, #232A08 brand text, #313E0C hero CTA text, and normalized #8C8C87 header gray. Preserve Syne, Space Grotesk, asymmetric layout and liquid chrome. Only contained 3D canvases remain dark. Remove marquees completely; do not reintroduce top or footer scrolling text.
- Reuse `src/tokens.css`, shared components and `src/acid.css` plus last-loaded `src/fresh.css`. Readable task text, prices, times, training records and clear focus states take precedence over decorative distortion.
- Offer global decorative-motion pause and honor reduced motion. Decorative content must not block clicks or create business records.

## Product and data

- P0: home, coach discovery / detail, booking, demo AI chat, child profiles, course records and an interactive data-backed growth universe.
- Preserve the local persistent API, centralized access in `src/api.js`, and child-context isolation.
- Only the separate test-coach workflow may confirm course completion. A persisted training record creates a clickable star and deduplicated growth event. Refreshes retain stars; animation replay never adds records.
- Explicitly identify synthetic people, child profiles, experience, credentials, courses, prices and feedback. Do not imply a live LLM, real authentication, payment or a production backend.

## Runtime and verification

- Build UI in `src/`; run the existing local dev server and verify in the available browser yourself.
- Before substantial redesign, clarify only missing design context using the Product Design `get-context` skill. Record durable user changes in these instructions and DESIGN.md.
- Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact.
- Run `npm run build` and `npm run test:sites` before any Sites handoff. Builds must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
- A static Sites build does not host the Node API. Do not deploy or claim a complete online platform without a suitable backend and user authorization.
