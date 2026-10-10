# Native liquid transition

Reference: https://libraries.dev/gooey
Source commit: https://github.com/Jakubantalik/Libraries.dev/tree/bcaf88f8a16a75fd95bf21e0747193ee3380a927/packages/liquid-gooey
License: MIT (included).

`src/spring.ts`, `src/filter.tsx`, and `src/geometry.ts` are unmodified upstream sources. `native.ts` samples the actual upstream bouncy/smooth spring compiler for Qt Quick. `ui/LiquidMotion.js` is built with `node scripts/orb-build/build.mjs`.

The DOM/React renderer is not used. The Gaussian blur and alpha threshold from `filter.tsx` are implemented as two native GPU shader passes in `ui/shaders/`. They merge independently moving camera, neck, body and satellite shapes. Their contrast crossing is the upstream 5/12 threshold; derivative antialiasing adds the app's fine border. Text and the thinking orb stay outside the filtered layer.

Additional technique reference: https://tympanus.net/codrops/2015/03/10/creative-gooey-effects/

Rebuild shaders with `./scripts/build-shaders.sh`. Qt's qsb tool is needed only when rebuilding, not at runtime.
