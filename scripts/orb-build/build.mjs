import { build } from 'esbuild';
import { writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
await build({ entryPoints: [root + 'vendor/thinking-orbs/native.ts'], bundle: true,
  format: 'iife', globalName: 'ThinkingOrbs', target: 'es2017',
  outfile: root + 'ui/ThinkingOrbs.js',
  banner: {js: '// Libraries.dev thinking-orbs — MIT, Copyright (c) 2026 Jakub Antalik.\n// See vendor/thinking-orbs/LICENSE and SOURCE.md. Generated; do not edit.'},
});
