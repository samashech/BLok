# Upstream

Source: https://github.com/Jakubantalik/Libraries.dev/tree/b7f44b8744f4e09ff088d824719636a513110e2a/packages/thinking-orbs

Requested library: https://libraries.dev/orbs

The `src/` files are unmodified upstream geometry, profiles, presets and types. `native.ts` binds the original frame generator and painter to Qt Quick Canvas. All nine animation states and the original 64 px tuning are retained. React and a browser runtime are not required.

Build: `npm ci --prefix scripts/orb-build && node scripts/orb-build/build.mjs`.
The committed `ui/ThinkingOrbs.js` runs without Node at app runtime.

License: MIT; see LICENSE in this directory. Copyright (c) 2026 Jakub Antalik.
