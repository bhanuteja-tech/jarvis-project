// Advanced SVG avatar controller — THE primary active avatar.
// Layered SVG + CSS state classes + optional rAF particles. All motion is
// event/state driven; particles run only during pipeline states and are
// disabled under prefers-reduced-motion.

import { ParticleField } from "./particles.js";

export const AVATAR_STATES = [
  "idle", "listening", "thinking", "searching", "analyzing",
  "matching", "tailoring", "validating", "speaking", "success", "error",
];

const STATE_CLASS = "avatar-state";
const PARTICLE_STATES = new Set([
  "thinking", "searching", "analyzing", "matching", "tailoring", "validating",
]);

export class AvatarController {
  constructor(container) {
    this.container = container;
    this.reducedMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    container.classList.add("avatar-stage");
    container.innerHTML = `<div class="particle-layer"></div>${AVATAR_SVG}`;
    this.svg = container.querySelector("svg");
    this.particles = new ParticleField(container.querySelector(".particle-layer"));
    this._state = null;
    this.setState("idle");
  }

  setState(next) {
    if (!AVATAR_STATES.includes(next) || this._state === next) return false;
    this._state = next;

    for (const cls of Array.from(this.svg.classList)) {
      if (cls.startsWith(STATE_CLASS)) this.svg.classList.remove(cls);
    }
    // The CSS targets `.avatar-state-<state>` on the svg root.
    this.svg.classList.add(`${STATE_CLASS}-${next}`);

    if (!this.reducedMotion && PARTICLE_STATES.has(next)) {
      this.particles.start(next);
    } else {
      this.particles.stop();
    }
    return true;
  }

  get state() {
    return this._state;
  }
}

const AVATAR_SVG = `
<svg viewBox="0 0 200 200" width="100%" height="100%" aria-hidden="true">
  <defs>
    <radialGradient id="core-grad" cx="50%" cy="45%">
      <stop offset="0%" stop-color="#9ecbff"/>
      <stop offset="55%" stop-color="#4a90d9"/>
      <stop offset="100%" stop-color="#1a2a44"/>
    </radialGradient>
    <filter id="soft-glow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <g class="orbit-ring" filter="url(#soft-glow)">
    <circle cx="100" cy="100" r="78" fill="none" stroke="#58a6ff"
            stroke-opacity=".25" stroke-width="1.5" stroke-dasharray="4 10"/>
    <circle class="orbit-dot" cx="178" cy="100" r="3.5" fill="#79c0ff"/>
    <circle class="orbit-dot orbit-dot--delay" cx="22" cy="100" r="2.5" fill="#79c0ff"/>
  </g>

  <g class="waveform" opacity="0">
    <rect class="wf" x="62" y="150" width="5" rx="2" height="12"/>
    <rect class="wf" x="74" y="150" width="5" rx="2" height="20"/>
    <rect class="wf" x="86" y="150" width="5" rx="2" height="14"/>
    <rect class="wf" x="98" y="150" width="5" rx="2" height="26"/>
    <rect class="wf" x="110" y="150" width="5" rx="2" height="18"/>
    <rect class="wf" x="122" y="150" width="5" rx="2" height="24"/>
    <rect class="wf" x="134" y="150" width="5" rx="2" height="10"/>
  </g>

  <g class="face" filter="url(#soft-glow)">
    <circle class="halo" cx="100" cy="88" r="52" fill="none"
            stroke="#58a6ff" stroke-opacity=".15" stroke-width="8"/>
    <circle class="core" cx="100" cy="88" r="40" fill="url(#core-grad)"
            stroke="#79c0ff" stroke-width="1.5"/>

    <g class="eyes">
      <ellipse class="eye eye--l" cx="84" cy="80" rx="7" ry="9" fill="#dff3ff"/>
      <ellipse class="eye eye--r" cx="116" cy="80" rx="7" ry="9" fill="#dff3ff"/>
    </g>

    <path class="scan-line" d="M64 88 H136" stroke="#c9e7ff" stroke-width="1"
          opacity="0"/>

    <path class="mouth" d="M86 104 Q100 112 114 104" fill="none"
          stroke="#dff3ff" stroke-width="3" stroke-linecap="round"/>
  </g>
</svg>
`;
