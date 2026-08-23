// Futuristic AI-agent avatar: layered SVG + CSS states + optional rAF
// particles. All animation is event/state driven; particles run only while
// the avatar is in an active state and are disabled under reduced-motion.

import { ParticleField } from "./particles.js";

const STATE_CLASS = "avatar-state";

export class AvatarController {
  constructor(container) {
    this.container = container;
    this.reducedMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    container.innerHTML = AVATAR_SVG;
    this.svg = container.querySelector("svg");
    this.core = container.querySelector(".core");
    this.particles = new ParticleField(container.querySelector(".particle-layer"));
    this.setState("idle");
  }

  setState(state) {
    if (this._state === state) return;
    this._state = state;

    const root = this.svg;
    for (const cls of Array.from(root.classList)) {
      if (cls.startsWith(STATE_CLASS)) root.classList.remove(cls);
    }
    root.classList.add(`${STATE_CLASS}-${state}`);

    const activeStates = new Set([
      "thinking", "searching", "analyzing", "matching",
      "tailoring", "validating", "executing",
    ]);
    if (!this.reducedMotion && activeStates.has(state)) {
      this.particles.start(state);
    } else {
      this.particles.stop();
    }
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
