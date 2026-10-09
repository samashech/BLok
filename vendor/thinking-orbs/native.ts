// Native Canvas binding of Libraries.dev's original geometry and painter.
import { frameBraid } from './src/engine/braid';
import { frameGlobe, frameRubik, frameWave } from './src/engine/lattice';
import { frameMorph } from './src/engine/morph';
import { frameOrbits } from './src/engine/orbits';
import { frameRibbon } from './src/engine/ribbon';
import { frameWeb } from './src/engine/web';
const MODE_FRAMES = {orbits: frameOrbits, globe: frameGlobe, rubik: frameRubik,
    wave: frameWave, web: frameWeb, braid: frameBraid, ribbon: frameRibbon,
    ring: frameRibbon, morph: frameMorph};
import { paintFrame } from './src/engine/core';
import { resolvePreset } from './src/presets';
import type { OrbState } from './src/types';
export function frame(state: OrbState, time: number) {
  const preset = resolvePreset(state, 64);
  return MODE_FRAMES[preset.mode](64, time * preset.speed, preset.opts);
}
export function draw(ctx: CanvasRenderingContext2D, state: OrbState, time: number) {
  paintFrame(ctx, frame(state, time), true, { r: 223, g: 230, b: 255 });
}
