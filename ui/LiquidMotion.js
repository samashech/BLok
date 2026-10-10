// Libraries.dev liquid-gooey — MIT. See vendor/liquid-gooey/LICENSE.
// Qt supports sampled timing curves natively; advertise that to the spring compiler.
var CSS = { supports: function() { return true; } };
var LiquidMotion = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __getOwnPropSymbols = Object.getOwnPropertySymbols;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __propIsEnum = Object.prototype.propertyIsEnumerable;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __spreadValues = (a, b) => {
    for (var prop in b || (b = {}))
      if (__hasOwnProp.call(b, prop))
        __defNormalProp(a, prop, b[prop]);
    if (__getOwnPropSymbols)
      for (var prop of __getOwnPropSymbols(b)) {
        if (__propIsEnum.call(b, prop))
          __defNormalProp(a, prop, b[prop]);
      }
    return a;
  };
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // vendor/liquid-gooey/native.ts
  var native_exports = {};
  __export(native_exports, {
    spring: () => spring
  });

  // vendor/liquid-gooey/src/spring.ts
  var presets = {
    snappy: { stiffness: 480, damping: 34, mass: 1 },
    smooth: { stiffness: 190, damping: 26, mass: 1 },
    bouncy: { stiffness: 320, damping: 17, mass: 1 }
  };
  var DT = 1 / 240;
  function simulate(c) {
    let x = 0;
    let v = 0;
    let t = 0;
    let settledAt = -1;
    let max = 0;
    const xs = [0];
    while (t < 10) {
      const a = (-c.stiffness * (x - 1) - c.damping * v) / c.mass;
      v += a * DT;
      x += v * DT;
      t += DT;
      xs.push(x);
      if (x > max) max = x;
      if (Math.abs(x - 1) < 1e-3 && Math.abs(v) < 0.02) {
        if (settledAt < 0) settledAt = t;
        if (t - settledAt >= 0.064) break;
      } else {
        settledAt = -1;
      }
    }
    const duration = settledAt > 0 ? settledAt : t;
    const n = Math.round(Math.min(120, Math.max(24, duration * 90)));
    const lastIdx = Math.min(xs.length - 1, duration / DT);
    const values = [];
    for (let i = 0; i <= n; i++) {
      const idx = Math.min(xs.length - 1, Math.round(i / n * lastIdx));
      values.push(Math.round(xs[idx] * 1e4) / 1e4);
    }
    values[values.length - 1] = 1;
    return { duration, values, overshoots: max > 1.001 };
  }
  var linearOK = null;
  function supportsLinear() {
    if (linearOK == null) {
      linearOK = typeof CSS !== "undefined" && typeof CSS.supports === "function" && CSS.supports("transition-timing-function", "linear(0, 1)");
    }
    return linearOK;
  }
  var cache = /* @__PURE__ */ new Map();
  var evalCache = /* @__PURE__ */ new Map();
  function easingFunction(spec) {
    let fn = evalCache.get(spec);
    if (fn) return fn;
    const lin = /^linear\(([^)]+)\)$/.exec(spec.trim());
    const bez = /^cubic-bezier\(([^)]+)\)$/.exec(spec.trim());
    if (lin) {
      const values = lin[1].split(",").map(Number);
      fn = (t) => {
        if (t <= 0) return values[0];
        if (t >= 1) return values[values.length - 1];
        const f = t * (values.length - 1);
        const i = Math.floor(f);
        return values[i] + (values[i + 1] - values[i]) * (f - i);
      };
    } else if (bez) {
      const [x1, y1, x2, y2] = bez[1].split(",").map(Number);
      fn = (t) => {
        if (t <= 0) return 0;
        if (t >= 1) return 1;
        let lo = 0;
        let hi = 1;
        for (let i = 0; i < 24; i++) {
          const mid = (lo + hi) / 2;
          const xm = 3 * mid * (1 - mid) * (1 - mid) * x1 + 3 * mid * mid * (1 - mid) * x2 + mid ** 3;
          if (xm < t) lo = mid;
          else hi = mid;
        }
        const u = (lo + hi) / 2;
        return 3 * u * (1 - u) * (1 - u) * y1 + 3 * u * u * (1 - u) * y2 + u ** 3;
      };
    } else if (spec === "ease") {
      fn = easingFunction("cubic-bezier(0.25, 0.1, 0.25, 1)");
    } else if (spec === "ease-in") {
      fn = easingFunction("cubic-bezier(0.42, 0, 1, 1)");
    } else if (spec === "ease-out") {
      fn = easingFunction("cubic-bezier(0, 0, 0.58, 1)");
    } else if (spec === "ease-in-out") {
      fn = easingFunction("cubic-bezier(0.42, 0, 0.58, 1)");
    } else {
      fn = (t) => Math.min(1, Math.max(0, t));
    }
    evalCache.set(spec, fn);
    return fn;
  }
  function resolveTransition(t, reducedMotion = false) {
    var _a;
    if (reducedMotion) return { duration: 0, easing: "linear" };
    const cfg = t != null ? t : "smooth";
    if (typeof cfg === "object" && "duration" in cfg) {
      return {
        duration: cfg.duration,
        easing: (_a = cfg.ease) != null ? _a : "cubic-bezier(0.22, 1, 0.36, 1)"
      };
    }
    const spring2 = typeof cfg === "string" ? presets[cfg] : __spreadValues({ stiffness: 300, damping: 24, mass: 1 }, cfg);
    const key = `${spring2.stiffness}/${spring2.damping}/${spring2.mass}/${supportsLinear()}`;
    let resolved = cache.get(key);
    if (!resolved) {
      const sim = simulate(spring2);
      resolved = {
        duration: Math.round(sim.duration * 1e3),
        easing: supportsLinear() ? `linear(${sim.values.join(", ")})` : sim.overshoots ? "cubic-bezier(0.34, 1.56, 0.64, 1)" : "cubic-bezier(0.22, 1, 0.36, 1)"
      };
      cache.set(key, resolved);
    }
    return resolved;
  }

  // vendor/liquid-gooey/native.ts
  var bounce = resolveTransition("bouncy");
  var smooth = resolveTransition("smooth");
  var bouncyCurve = easingFunction(bounce.easing);
  var smoothCurve = easingFunction(smooth.easing);
  function spring(t, bouncy = true) {
    return (bouncy ? bouncyCurve : smoothCurve)(Math.max(0, Math.min(1, t)));
  }
  return __toCommonJS(native_exports);
})();
