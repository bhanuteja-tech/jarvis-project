// Lightweight orbital particles (rAF, only while active states run).
// Disabled automatically under prefers-reduced-motion.

const COUNT = 10;
const RADIUS = 70;
const SPEED = 0.02;

export class ParticleField {
  constructor(layerElement) {
    this.layer = layerElement;
    this.dots = [];
    this.angle = Math.random() * Math.PI * 2;
    this.running = false;
    this._raf = null;

    const reduced =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reduced) return;

    for (let i = 0; i < COUNT; i++) {
      const circle = document.createElementNS(
        "http://www.w3.org/2000/svg", "circle"
      );
      circle.setAttribute("r", (1.5 + Math.random() * 2).toFixed(1));
      circle.setAttribute("fill", "#79c0ff");
      circle.setAttribute("opacity", "0");
      layerElement.appendChild(circle);
      this.dots.push({
        el: circle,
        offset: (i / COUNT) * Math.PI * 2,
        wobble: Math.random() * Math.PI,
      });
    }
  }

  start(state) {
    if (!this.dots.length || this.running) return;
    this.running = true;
    this.speed = SPEED * (state === "executing" ? 2 : 1);
    this._tick();
  }

  stop() {
    this.running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
    for (const dot of this.dots) dot.el.setAttribute("opacity", "0");
  }

  _tick = () => {
    if (!this.running) return;
    this.angle += this.speed ?? 0.02;
    for (const dot of this.dots) {
      const a = this.angle + dot.offset;
      const r = RADIUS + Math.sin(this.angle * 3 + dot.wobble) * 6;
      const x = 100 + Math.cos(a) * r;
      const y = 100 + Math.sin(a) * r * 0.9;
      dot.el.setAttribute("cx", x.toFixed(1));
      dot.el.setAttribute("cy", y.toFixed(1));
      dot.el.setAttribute("opacity", "0.7");
    }
    this._raf = requestAnimationFrame(() => this._tick());
  };
}
