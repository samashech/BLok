// Sample the upstream spring compiler on Qt's shared animation clock.
import { resolveTransition, easingFunction } from './src/spring';
const bounce = resolveTransition('bouncy');
const smooth = resolveTransition('smooth');
const bouncyCurve = easingFunction(bounce.easing);
const smoothCurve = easingFunction(smooth.easing);
export function spring(t: number, bouncy = true) {
    return (bouncy ? bouncyCurve : smoothCurve)(Math.max(0, Math.min(1, t)));
}
