import { build } from 'esbuild';
import { writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
await build({ entryPoints: [root + 'vendor/thinking-orbs/native.ts'], bundle: true,
  format: 'iife', globalName: 'ThinkingOrbs', target: 'es2017',
  outfile: root + 'ui/ThinkingOrbs.js',
  banner: {js: '// Libraries.dev thinking-orbs — MIT, Copyright (c) 2026 Jakub Antalik.\n// See vendor/thinking-orbs/LICENSE and SOURCE.md. Generated; do not edit.'},
});
await build({entryPoints: [root + 'vendor/liquid-gooey/native.ts'], bundle: true,
  format: 'iife', globalName: 'LiquidMotion', target: 'es2017',
  outfile: root + 'ui/LiquidMotion.js',
  banner: {js: '// Libraries.dev liquid-gooey — MIT. See vendor/liquid-gooey/LICENSE.\n// Qt supports sampled timing curves natively; advertise that to the spring compiler.\nvar CSS = { supports: function() { return true; } };'},
});
