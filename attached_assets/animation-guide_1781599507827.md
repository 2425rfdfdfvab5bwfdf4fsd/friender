# The Complete Web Animation Guide
> **Version 2.0** — Researched & Updated June 2025  
> Covers 15 project categories · 8 libraries · Performance rules · Accessibility · Code patterns

---

## Table of Contents

1. [Why Animation Matters](#1-why-animation-matters)
2. [How Browsers Render Animation — The Pipeline](#2-how-browsers-render-animation--the-pipeline)
3. [Golden Performance Rules](#3-golden-performance-rules)
4. [Accessibility — prefers-reduced-motion](#4-accessibility--prefers-reduced-motion)
5. [Animation Timing & Easing Reference](#5-animation-timing--easing-reference)
6. [Library Decision Framework](#6-library-decision-framework)
7. [Category-by-Category Animation Playbook](#7-category-by-category-animation-playbook)
   - [1. Portfolio / Developer Sites](#-1-portfolio--developer-sites)
   - [2. AI / SaaS / Tech Startups](#-2-ai--saas--tech-startups)
   - [3. E-Commerce](#-3-e-commerce)
   - [4. Business / Agency](#-4-business--agency)
   - [5. Dashboard / Admin Panel](#-5-dashboard--admin-panel)
   - [6. Finance / Crypto / Banking](#-6-finance--crypto--banking)
   - [7. Education / LMS](#-7-education--lms)
   - [8. Healthcare / Medical](#-8-healthcare--medical)
   - [9. Real Estate](#-9-real-estate)
   - [10. Restaurant / Food Delivery](#-10-restaurant--food-delivery)
   - [11. Travel / Hotel Booking](#-11-travel--hotel-booking)
   - [12. Gaming / Entertainment](#-12-gaming--entertainment)
   - [13. App Landing Pages](#-13-app-landing-pages)
   - [14. Loading Animations](#-14-loading-animations)
   - [15. Micro-Interactions](#-15-micro-interactions)
8. [2025 Trend Spotlight](#8-2025-trend-spotlight)
9. [Implementation Code Patterns](#9-implementation-code-patterns)
10. [Quick-Pick Reference Card](#10-quick-pick-reference-card)

---

## 1. Why Animation Matters

Animation is not decoration — it is communication. When done right, motion tells users:
- **Where to look** (attention direction)
- **What happened** (state feedback)
- **How things are related** (spatial context)
- **That the system is alive** (perceived responsiveness)

Done wrong, animation slows users down, causes physical discomfort (vestibular disorders affect ~35% of adults over 40), and signals an amateur product. This guide gives you the framework to do it right.

---

## 2. How Browsers Render Animation — The Pipeline

Understanding this pipeline is the single most important thing you can learn about web animation performance.

```
JavaScript → Style → Layout → Paint → Composite
                                         ↑
                              GPU takes over here
```

The browser must complete all five steps to render each frame. At 60fps, you have **~16ms per frame**. The goal is to skip as many steps as possible:

| What you animate | Steps triggered | Cost |
|---|---|---|
| `width`, `height`, `top`, `left` | Layout → Paint → Composite | 🔴 Expensive — triggers full reflow |
| `background-color`, `color`, `box-shadow` | Paint → Composite | 🟡 Medium — triggers repaint |
| `transform`, `opacity` | Composite only | 🟢 Cheap — GPU only, never drops frames |
| `filter` | Composite (mostly) | 🟢 Usually cheap |

**The Rule:** Only animate `transform` and `opacity` in performance-critical animations. Everything else is a liability.

---

## 3. Golden Performance Rules

### Rule 1 — Stick to Composite Properties

```css
/* ❌ NEVER — triggers layout recalculation every frame */
.card:hover { width: 320px; left: 20px; }

/* ✅ ALWAYS — GPU composited, zero layout cost */
.card:hover { transform: translateX(20px) scaleX(1.05); }
```

### Rule 2 — Use `will-change` Surgically

`will-change` promotes an element to its own GPU layer *before* the animation starts, eliminating the layer-creation stutter. Use it only when you actually see jank — overuse causes excessive memory usage.

```css
/* Add will-change only to elements you know will animate */
.hero-card { will-change: transform; }

/* Remove it after the animation completes */
element.addEventListener('animationend', () => {
  element.style.willChange = 'auto';
});
```

### Rule 3 — Keep Animated Elements on Their Own Layer

When an element animates, every other element painted on the same layer gets repainted too. Isolate heavy animators with:

```css
.heavy-animator {
  will-change: transform;
  /* Or the older hack: */
  transform: translateZ(0);
}
```

### Rule 4 — Respect 120Hz Displays

Modern devices (ProMotion Macs, many Android phones) run at 120fps, giving you only **8ms per frame**. CSS animations and the Web Animations API run on the compositor thread and automatically adapt. JavaScript-driven animations via `requestAnimationFrame` also adapt. Libraries like GSAP and Motion both support 120fps natively.

### Rule 5 — Test on Mid-Range Hardware

Always test animations on a mid-range Android phone or use Chrome DevTools CPU throttling (6x slowdown). What feels smooth on a M3 MacBook Pro can be a slideshow on a $200 Android device.

---

## 4. Accessibility — prefers-reduced-motion

Approximately **1 in 3 adults** will experience a vestibular disorder in their lifetime. Large-scale motion — parallax, zooming, spinning, sliding — can trigger dizziness, nausea, and migraines. Users can signal this preference at the OS level; your CSS and JavaScript must respect it.

### WCAG Requirements

| Criterion | Level | What It Means |
|---|---|---|
| SC 2.3.3 — Animation from Interactions | AAA | Non-essential motion triggered by interaction must be disableable |
| SC 2.2.2 — Pause, Stop, Hide | A | Auto-playing looping content needs pause controls |

### The CSS Pattern (Most Important)

```css
/* Base animation — applies to everyone */
.hero-text {
  animation: fadeSlideUp 600ms ease-out both;
}

/* Override for users who prefer reduced motion */
@media (prefers-reduced-motion: reduce) {
  .hero-text {
    /* Option A: Remove all motion, keep the end state */
    animation: none;
    
    /* Option B: Fade only — no movement, still communicates state */
    animation: fadeOnly 300ms ease-out both;
  }
  
  @keyframes fadeOnly {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
}
```

### The JavaScript Pattern

```javascript
// Check the preference in JS
const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Framer Motion — automatic with `useReducedMotion`
import { useReducedMotion } from 'motion/react';
const shouldReduce = useReducedMotion();
const variants = {
  hidden: { opacity: 0, y: shouldReduce ? 0 : 40 },
  visible: { opacity: 1, y: 0 }
};

// GSAP — manual check
if (!prefersReduced) {
  gsap.from('.hero', { y: 60, opacity: 0, duration: 0.8 });
} else {
  gsap.from('.hero', { opacity: 0, duration: 0.4 }); // fade only
}
```

### Common Mistakes

- ❌ Treating `prefers-reduced-motion` as a kill-switch for all animation — fades and opacity changes are fine
- ❌ Forgetting it for `Three.js` / canvas-based animations (you must check it manually)
- ❌ Not testing with the setting actually enabled in your OS

---

## 5. Animation Timing & Easing Reference

### Duration Table (from NN/Group + Google Material Design 3)

| Animation Type | Duration | Notes |
|---|---|---|
| Button press / toggle | 100–150ms | Feels instant but visible |
| Tooltip / small popover | 150–200ms | Quick acknowledgment |
| Dropdown menu | 150–250ms | Open fast, close slightly slower |
| Card hover lift | 150–250ms | Snappy, not jumpy |
| Modal / sheet enter | 250–400ms | Large element, needs more time |
| Scroll-reveal element | 400–600ms | Deliberate, readable |
| Page / route transition | 500–700ms | Spatial orientation |
| Multi-element choreograph | 500–800ms + stagger | Sequence reads as a story |
| Looping hero background | 4000–8000ms | Slow enough not to distract |

**The 500ms Rule:** Any user-triggered animation over 500ms will feel slow. Reserve longer durations for system-initiated transitions (route changes, modal entrances) where the user expects to wait.

### Easing Quick Reference

```css
/* ENTERING the screen — start fast, ease out gently */
.entering { transition: transform 300ms cubic-bezier(0, 0, 0.2, 1); }
/* Google's "Decelerate" — the most commonly correct choice */

/* EXITING the screen — start slow, accelerate out */
.exiting  { transition: transform 250ms cubic-bezier(0.4, 0, 1, 1); }
/* Google's "Accelerate" — departure feels intentional */

/* STAYING on screen — both ends ease */
.shifting { transition: transform 400ms cubic-bezier(0.4, 0, 0.2, 1); }
/* Google's "Standard" — use for most repositioning */

/* SPRINGY feedback — overshoot for personality */
.bouncy   { transition: transform 500ms cubic-bezier(0.34, 1.56, 0.64, 1); }
/* Use for success states, micro-interactions, not navigation */

/* LINEAR — almost never correct for UI */
/* Use only for: opacity pulses, looping backgrounds, progress bars */
.pulse    { animation: pulse 2s linear infinite; }
```

### Stagger Delay Reference

When revealing multiple elements (card grids, list items):

```javascript
// Sweet spot: 50–100ms between items, never exceed 8 items
// After 8 items the delay becomes annoying, just animate them all at once

const stagger = 60; // ms
items.forEach((item, i) => {
  item.style.animationDelay = `${i * stagger}ms`;
});

// Framer Motion
<motion.ul>
  {items.map((item, i) => (
    <motion.li
      key={i}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.06, duration: 0.4 }}
    />
  ))}
</motion.ul>
```

---

## 6. Library Decision Framework

### Comparison Table (June 2025)

| Library | Gzipped Size | Perf Ceiling | React DX | Interactivity | Best For |
|---|---|---|---|---|---|
| **CSS Keyframes** | 0 KB | 🟢 Highest (compositor) | Manual | Low | Simple, perf-critical animations |
| **CSS Scroll-Driven** | 0 KB | 🟢 Highest (off main thread) | Manual | Medium | Scroll-linked effects, no JS needed |
| **Motion (Framer Motion)** | ~30–34 KB | 🟢 Excellent | 🏆 Best | Medium | React/Next.js UI — the default choice |
| **GSAP** | ~23–27 KB core | 🟢 Best for complex timelines | Manual hooks | Low-Medium | Complex sequences, SVG, ScrollTrigger |
| **Rive** | Runtime ~40 KB | 🟢 GPU-accelerated | Wrapper | 🏆 Best | Interactive animated characters/icons |
| **LottieFiles** | ~60 KB player | 🟡 CPU-based | Wrapper | Low | After Effects exports, icon animations |
| **Three.js / R3F** | ~580 KB | Depends on scene | R3F | Medium | 3D scenes, WebGL, particles |
| **Anime.js v4** | ~10 KB | 🟡 JS tween engine | Manual | Low | Lightweight alternative to GSAP |

### Decision Tree

```
Are you building in React/Next.js?
├── YES → Start with Motion (Framer Motion)
│         ├── Need complex timelines or ScrollTrigger? → Add GSAP
│         ├── Need 3D / WebGL? → Use React Three Fiber (R3F)
│         └── Need interactive animated mascots/icons? → Use Rive
│
└── NO (Vanilla JS / Vue / Svelte)
          ├── Complex timelines needed? → GSAP
          ├── Interactive animations? → Rive
          ├── Lightweight, simple? → Anime.js or CSS
          └── Scroll-linked effects? → CSS Scroll-Driven Animations (no library needed)
```

### Library Deep Notes

**Motion (formerly Framer Motion)**  
Rebranded in late 2024 to `motion` (npm: `motion`). The `framer-motion` package still works. At ~30KB gzipped its all-in-one package often beats GSAP core + plugins combined for React apps. The `LazyMotion` component can defer the animation engine to reduce initial bundle. The `useReducedMotion()` hook handles accessibility automatically.

**GSAP**  
Still unmatched for complex multi-element timelines and ScrollTrigger sequences. The `@gsap/react` package introduced `useGSAP()` in 2024 — always use it instead of `useEffect` for automatic cleanup. Core is free; premium plugins (MorphSVG, SplitText, DrawSVG) require a paid Club GSAP license.

**Rive**  
10–15× smaller file size than Lottie for equivalent animations. GPU-accelerated via WebGL2. The State Machine makes it possible to drive animations from user input without JavaScript logic. Released data binding in April 2025 — you can now bind real app data (price, username, score) directly to animation properties. Best for animated icons, mascots, and game-like UI.

**LottieFiles**  
The easiest path from After Effects to web. Massive library of 4.2M+ community animations. Downside: CPU-based rendering can cause jank on complex animations and the JSON format gets bloated. Best for simple icon animations, loaders, and onboarding illustrations. dotLottie (`.lottie` binary format) is ~10× smaller than JSON.

**CSS Scroll-Driven Animations (2025 Native API)**  
No library needed. Runs entirely off the main thread. `animation-timeline: scroll()` ties animation progress to scroll position; `animation-timeline: view()` ties it to element visibility (the CSS version of IntersectionObserver). Chrome/Edge support is solid; Safari support landed in 2025. For production use with broad browser support, pair with a `@supports` check.

---

## 7. Category-by-Category Animation Playbook

Each category includes: the best animations to use, which to skip, recommended library, timing guidelines, and a starter code snippet.

---

### 🧑‍💻 1. Portfolio / Developer Sites

**Tone:** Impressive but not distracting. The work is the hero — animation supports context.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Typing text (role/tagline) | Hero | CSS + JS | 80–120ms/char |
| Scroll-reveal sections | All sections | Motion / AOS | 500ms ease-out |
| Magnetic cursor effect | Global | Vanilla JS | ~100ms follow lag |
| Glassmorphism card hover | Project cards | CSS | 200ms ease-out |
| Tech stack orbit | Skills section | CSS / Three.js | 8–12s loop |
| Terminal command animation | About/hero | CSS keyframes | 60–100ms/char |
| Particle constellation | Hero background | Three.js / tsParticles | 8s cycle |

#### Skip These
- Auto-playing Neural Network that dominates the hero (users can't read your name)
- 3D avatar that loads for 5 seconds on mobile
- Scroll-hijacking (custom scroll speeds always annoy users)

#### Recommended Stack
**Primary:** Motion (Framer Motion) + CSS keyframes  
**For 3D hero:** React Three Fiber + drei

#### Starter — Scroll Reveal (Motion)
```jsx
import { motion } from 'motion/react';

const Section = ({ children }) => (
  <motion.section
    initial={{ opacity: 0, y: 40 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, amount: 0.2 }}
    transition={{ duration: 0.6, ease: [0, 0, 0.2, 1] }}
  >
    {children}
  </motion.section>
);
```

#### Starter — Typing Animation (CSS)
```css
.typing-text {
  overflow: hidden;
  white-space: nowrap;
  border-right: 2px solid currentColor;
  animation:
    typing 2.5s steps(30) forwards,
    blink 0.75s step-end infinite;
}
@keyframes typing { from { width: 0 } to { width: 100% } }
@keyframes blink { 50% { border-color: transparent } }
```

---

### 🤖 2. AI / SaaS / Tech Startups

**Tone:** Futuristic, intelligent, trustworthy. Animation should demonstrate the product's capability.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Prompt-to-output flow | Hero / feature | Motion + SVG | 600ms sequence |
| Animated AI chat bubble | Feature demo | Motion | 300ms appear |
| Data flow lines (SVG) | Architecture diagram | GSAP DrawSVG / CSS | 1.5s draw |
| Voice waveform | Audio feature | Canvas / Rive | 60fps real-time |
| Gradient blob hero | Background | CSS keyframes | 6–8s morph loop |
| Number counter (metric) | Social proof | Motion / GSAP | 1.5–2s count-up |
| Feature card hover lift | Pricing / feature grid | CSS | 200ms ease-out |

#### Skip These
- Cyber grid backgrounds that make text illegible
- Scanning radar on every page (becomes visual noise)
- Holographic effects that don't work on non-retina screens

#### Recommended Stack
**Primary:** Motion (Framer Motion)  
**For SVG paths / complex sequences:** GSAP  
**For mascot/logo:** Rive

#### Starter — Gradient Blob Hero (CSS)
```css
.blob-bg {
  background: radial-gradient(ellipse at 20% 50%, #6366f1 0%, transparent 60%),
              radial-gradient(ellipse at 80% 20%, #8b5cf6 0%, transparent 60%),
              radial-gradient(ellipse at 50% 80%, #06b6d4 0%, transparent 60%),
              #0f172a;
  animation: blobShift 8s ease-in-out infinite alternate;
}
@keyframes blobShift {
  0%   { background-position: 20% 50%, 80% 20%, 50% 80%; }
  100% { background-position: 40% 30%, 60% 60%, 30% 70%; }
}
```

#### Starter — Count-Up on Scroll (Motion)
```jsx
import { useInView, useMotionValue, useSpring, useTransform } from 'motion/react';
import { useEffect, useRef } from 'react';

const Counter = ({ target }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const raw = useMotionValue(0);
  const spring = useSpring(raw, { stiffness: 80, damping: 20 });
  const rounded = useTransform(spring, v => Math.round(v).toLocaleString());

  useEffect(() => { if (inView) raw.set(target); }, [inView, target]);

  return <motion.span ref={ref}>{rounded}</motion.span>;
};
```

---

### 🛍️ 3. E-Commerce

**Tone:** Delightful but fast. Every animation must serve the purchase journey — never slow it down.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Add-to-cart fly effect | Product → cart icon | Motion / GSAP | 600ms arc |
| Product image zoom hover | Product card | CSS | 300ms ease-out |
| Wishlist heart pop | Product card | CSS keyframes | 400ms spring |
| Cart success confetti | Post-add confirmation | Canvas Confetti | 2000ms burst |
| Checkout progress steps | Checkout flow | Motion | 300ms slide |
| Review stars fill | Rating display | CSS stagger | 400ms + 80ms stagger |
| Skeleton loading | Product grid | CSS shimmer | 1.5s linear loop |

#### Skip These
- Auto-playing sale banner that flashes (accessibility violation + annoying)
- Product 3D rotation that requires 50 images to load
- Parallax on product cards (makes prices hard to read while scrolling)

#### Recommended Stack
**Primary:** CSS keyframes + Motion for state transitions  
**For confetti / particle effects:** `canvas-confetti` (3KB)  
**For product 3D:** Three.js / model-viewer (if you have actual 3D models)

#### Starter — Wishlist Heart Pop (CSS)
```css
.heart-btn.active .heart-icon {
  animation: heartPop 400ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
  color: #ef4444;
}
@keyframes heartPop {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.4); }
  70%  { transform: scale(0.9); }
  100% { transform: scale(1.1); }
}
```

#### Starter — Skeleton Loading (CSS)
```css
.skeleton {
  background: linear-gradient(90deg, #e2e8f0 25%, #f8fafc 50%, #e2e8f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
  border-radius: 4px;
}
@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

---

### 🏢 4. Business / Agency

**Tone:** Polished, confident, professional. Animation builds trust — it should never surprise.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Fade-up section reveal | All sections | AOS / Motion | 500–600ms |
| Stats counter | Results section | GSAP / Motion | 1.5–2s ease-out |
| Client logo marquee | Social proof | CSS | 20–30s linear loop |
| Parallax hero | Above the fold | CSS / GSAP | 60fps scroll-linked |
| Service card hover lift | Services grid | CSS | 200ms ease-out |
| CTA pulse glow | Primary button | CSS | 1.5s ease-in-out |
| Process timeline draw | How it works | GSAP DrawSVG | 2s draw |

#### Skip These
- Floating geometric shapes that never stop moving (distracting during reading)
- Gradient mesh that shifts colors (causes eye fatigue on long pages)
- Team card flip on hover (users often accidentally trigger it)

#### Recommended Stack
**Primary:** CSS + AOS for scroll reveals (lightweight, fast to implement)  
**For complex SVG / timelines:** GSAP

#### Starter — Client Logo Marquee (CSS, no JS)
```css
.marquee-track {
  display: flex;
  gap: 3rem;
  animation: marquee 25s linear infinite;
  width: max-content;
}
.marquee-track:hover { animation-play-state: paused; }

@keyframes marquee {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}
/* Duplicate logos in HTML so the loop is seamless */
```

#### Starter — CTA Pulse
```css
.cta-button {
  position: relative;
}
.cta-button::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.6);
  animation: ctaPulse 1.5s ease-out infinite;
}
@keyframes ctaPulse {
  to { box-shadow: 0 0 0 16px rgba(99, 102, 241, 0); }
}
```

---

### 📊 5. Dashboard / Admin Panel

**Tone:** Informative, calm, responsive. Every animation should communicate data or state — not entertain.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Skeleton loading | All data-fetching areas | CSS shimmer | 1.5s loop |
| Chart line draw | Chart initial load | GSAP / Recharts built-in | 800ms ease-out |
| KPI count-up | Metric cards | Motion useSpring | 1.5–2s |
| Toast / notification slide-in | Global | Motion AnimatePresence | 300ms slide |
| Dark mode toggle | Header | Motion layout | 200ms |
| Sidebar expand/collapse | Navigation | Motion | 250ms ease-in-out |
| Progress ring | Task completion | CSS stroke-dashoffset | 600ms ease-out |

#### Skip These
- Animated chart backgrounds (distracts from the data)
- Live activity pulse on every metric (only use where data is genuinely real-time)
- Expanding card animation on click (users expect navigation, not panels)

#### Recommended Stack
**Primary:** Motion (Framer Motion) — `AnimatePresence` is essential for notification queues  
**For charts:** Recharts (built-in animations) or Chart.js with animation config

#### Starter — Toast with AnimatePresence (Motion)
```jsx
import { AnimatePresence, motion } from 'motion/react';

const Toast = ({ messages }) => (
  <div className="toast-container">
    <AnimatePresence>
      {messages.map(msg => (
        <motion.div
          key={msg.id}
          initial={{ opacity: 0, x: 60, scale: 0.95 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: 60 }}
          transition={{ duration: 0.3, ease: [0, 0, 0.2, 1] }}
          className="toast"
        >
          {msg.text}
        </motion.div>
      ))}
    </AnimatePresence>
  </div>
);
```

#### Starter — SVG Progress Ring (CSS)
```css
.progress-ring-circle {
  stroke-dasharray: 283; /* 2 * π * r (r=45) */
  stroke-dashoffset: calc(283 - (283 * var(--progress)) / 100);
  transition: stroke-dashoffset 600ms cubic-bezier(0.4, 0, 0.2, 1);
  transform: rotate(-90deg);
  transform-origin: center;
}
```

---

### 💰 6. Finance / Crypto / Banking

**Tone:** Precise, secure, trustworthy. Animation should reinforce data accuracy and security — never feel playful.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Balance count-up | Wallet/account view | Motion useSpring | 1–1.5s |
| Stock graph line draw | Chart load | GSAP / D3 | 1s ease-out |
| Transaction success checkmark | Post-transaction | CSS / Lottie | 500ms draw |
| Candlestick chart load | Trading view | D3 + GSAP | 600ms stagger |
| Secure shield pulse | Security sections | CSS | 2s ease-in-out |
| Card flip (front/back) | Card management | CSS 3D transform | 400ms ease-in-out |
| KYC step progress | Verification flow | Motion | 300ms slide |

#### Skip These
- Crypto coin floating animation (feels unprofessional for serious fintech)
- Blockchain node network animation on every page (high GPU cost, low information value)
- Any animation that fires during transaction processing (users need to see confirmation, not distraction)

#### Recommended Stack
**Primary:** CSS + Motion for UI states  
**For charts:** D3.js (transitions built in) or Recharts  
**For success states:** LottieFiles (checkmark, shield animations)

#### Starter — Credit Card Flip (CSS 3D)
```css
.card-wrapper { perspective: 1000px; }
.card-inner {
  position: relative;
  transform-style: preserve-3d;
  transition: transform 400ms ease-in-out;
}
.card-wrapper:hover .card-inner,
.card-wrapper.flipped .card-inner {
  transform: rotateY(180deg);
}
.card-front, .card-back {
  backface-visibility: hidden;
  position: absolute; inset: 0;
}
.card-back { transform: rotateY(180deg); }
```

---

### 🎓 7. Education / LMS

**Tone:** Encouraging, clear, celebratory on achievement. Animation guides learners without overwhelming.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Course progress ring | Student dashboard | CSS stroke | 600ms ease-out |
| Achievement badge pop | On unlock | CSS spring | 500ms overshoot |
| Quiz feedback animation | After answer | Motion | 300ms (correct = green scale, wrong = red shake) |
| Certificate reveal | On completion | Motion / GSAP | 1.2s cinematic |
| Learning path timeline | Course overview | Motion scroll | 400ms stagger |
| Video lesson thumbnail hover | Course catalog | CSS | 200ms |
| Animated quiz timer | Quiz page | CSS countdown | Linear, real-time |

#### Skip These
- Book opening animation that plays every time a lesson loads (annoying after the first time)
- Puzzle learning animation in navigation (cognitive overload)
- Confetti on every quiz answer (loses meaning fast)

#### Recommended Stack
**Primary:** Motion (Framer Motion) for React-based LMS  
**For achievement badges:** Rive (stateful, reusable, interactive)  
**For certificate reveal:** GSAP timeline (precise multi-step choreography)

#### Starter — Error Shake + Correct Scale (Motion)
```jsx
const feedbackVariants = {
  correct: { scale: [1, 1.08, 1], backgroundColor: '#dcfce7', transition: { duration: 0.4 } },
  wrong: {
    x: [0, -8, 8, -8, 8, 0],
    backgroundColor: '#fee2e2',
    transition: { duration: 0.4 }
  },
  idle: { scale: 1, x: 0, backgroundColor: '#ffffff' }
};
```

---

### 🏥 8. Healthcare / Medical

**Tone:** Calm, professional, reassuring. Motion should reduce anxiety, not add to it. Slower, gentler animations are the rule.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Heartbeat line | Hero / dashboard | SVG + CSS | 1–1.5s pulse |
| Appointment step progress | Booking flow | Motion | 300ms slide |
| Health tracker ring | Patient dashboard | CSS stroke | 800ms ease-out |
| Clean wave background | Hero | CSS | 8s gentle loop |
| Checkup step animation | Onboarding | Motion stagger | 400ms each |
| Doctor card hover | Provider directory | CSS | 200ms lift |
| Form validation feedback | All forms | Motion | 200ms (green checkmark / red shake) |

#### Skip These
- Body scan animation (can cause anxiety for patients)
- DNA helix spinning constantly in background (distracting)
- Emergency alert pulse on non-urgent content (desensitizes users)
- Anything that looks "fun" or "playful" (undermines medical credibility)

#### Recommended Stack
**Primary:** CSS + Motion — keep it minimal  
**For illustrations:** LottieFiles (medical illustration libraries available)

#### Starter — Heartbeat SVG (CSS)
```css
.heartbeat-line {
  stroke-dasharray: 300;
  stroke-dashoffset: 300;
  animation: drawHeartbeat 1.2s ease-in-out infinite;
}
@keyframes drawHeartbeat {
  0%   { stroke-dashoffset: 300; opacity: 0; }
  10%  { opacity: 1; }
  70%  { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: 0; opacity: 0; }
}
```

---

### 🏠 9. Real Estate

**Tone:** Aspirational, warm, trustworthy. Animation should help buyers picture themselves in the home.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Property card reveal | Listings grid | Motion scroll | 500ms stagger |
| Map pin drop | Property map | CSS / Leaflet | 300ms bounce |
| Image gallery slide | Property detail | Motion / Embla | 350ms ease-in-out |
| Mortgage calculator count-up | Calculator | Motion | 800ms |
| Virtual tour entry | 360° view trigger | Motion | 500ms zoom-in |
| Favorite heart pop | Listing card | CSS | 400ms spring |
| Search filter transition | Filter bar | Motion layout | 250ms |

#### Skip These
- 3D house rotation that requires a powerful GPU (most buyers are on phones)
- Building line-drawing animation on the homepage (takes too long to load)
- Neighborhood map animation that autoplays (users want to control the map)

#### Recommended Stack
**Primary:** Motion (Framer Motion) + CSS  
**For maps:** Mapbox GL / Leaflet (have built-in animation APIs)

#### Starter — Listing Card Reveal (Motion, staggered)
```jsx
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } }
};
const cardVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0, 0, 0.2, 1] } }
};

<motion.div variants={containerVariants} initial="hidden" whileInView="visible" viewport={{ once: true }}>
  {listings.map(l => <motion.div key={l.id} variants={cardVariants}><ListingCard {...l} /></motion.div>)}
</motion.div>
```

---

### 🍕 10. Restaurant / Food Delivery

**Tone:** Appetizing, energetic, warm. Animation should make food look irresistible.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Food plate reveal | Hero / menu | Motion | 500ms slide-up |
| Add-to-cart food pop | Menu items | CSS spring | 400ms |
| Order tracking progress | Order status | Motion | 300ms step |
| Delivery tracker (map) | Order page | Mapbox GL | Real-time |
| Menu card hover | Menu grid | CSS | 200ms lift + shadow |
| Steam rising animation | Food images | CSS keyframes | 2s ease-in-out loop |
| Reservation calendar motion | Booking | Motion | 250ms slide |

#### Skip These
- Pizza slice pull animation (cute but distracting and slow to implement)
- Cooking flame animation on every page load (heavy, annoying)
- Chef hat bounce in navigation (navigation should be instant and clear)

#### Recommended Stack
**Primary:** CSS + Motion  
**For order tracking:** Mapbox GL JS (real-time driver location)  
**For food illustrations:** Rive or LottieFiles

#### Starter — Steam Rising (CSS)
```css
.steam {
  position: absolute;
  top: -20px;
  width: 6px;
  height: 20px;
  border-radius: 50%;
  background: rgba(255,255,255,0.4);
  animation: steam 2s ease-in-out infinite;
}
.steam:nth-child(2) { animation-delay: 0.4s; left: 40%; }
.steam:nth-child(3) { animation-delay: 0.8s; left: 60%; }
@keyframes steam {
  0%   { transform: translateY(0) scaleX(1); opacity: 0.6; }
  100% { transform: translateY(-40px) scaleX(1.8); opacity: 0; }
}
```

---

### ✈️ 11. Travel / Hotel Booking

**Tone:** Dreamy, wanderlust-inducing, smooth. Animation should teleport the user to the destination.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Destination image parallax | Hero / destination cards | CSS scroll | Scroll-linked |
| Flying airplane path | Route display | SVG + GSAP MotionPath | 2–3s ease-in-out |
| Hotel card reveal | Listing grid | Motion stagger | 500ms |
| Booking confirmation | Post-booking | Lottie / Motion | 800ms celebratory |
| Date picker calendar motion | Search / booking | Motion | 250ms slide |
| Globe rotation | World destinations | Three.js | 30s slow loop |
| Beach wave background | Hero | CSS | 6s ease-in-out loop |

#### Skip These
- Suitcase packing animation that blocks the page (just show it in an illustration, not as a loader)
- Passport stamp animation on every page (clever once, annoying on repeat)
- Compass spin that doesn't mean anything (animation must carry information)

#### Recommended Stack
**Primary:** Motion + CSS  
**For airplane path:** GSAP MotionPath plugin  
**For globe:** Three.js (globe.gl library — great for interactive destination globes)

#### Starter — Beach Wave (CSS)
```css
.wave {
  position: absolute;
  bottom: 0;
  width: 200%;
  height: 80px;
  background: url("wave-svg-path");
  animation: wave 6s ease-in-out infinite;
}
.wave:nth-child(2) { animation: wave 8s ease-in-out infinite reverse; opacity: 0.5; }
@keyframes wave {
  0%, 100% { transform: translateX(0); }
  50%       { transform: translateX(-25%); }
}
```

---

### 🎮 12. Gaming / Entertainment

**Tone:** Intense, visceral, high-energy. This is the one context where "too much" barely exists.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Glitch text effect | Hero title | CSS keyframes | 150ms bursts |
| Neon glow pulsing | UI elements | CSS | 1.5s ease-in-out |
| Game card hover tilt (3D) | Game cards | Vanilla JS + CSS | Real-time mouse |
| XP progress bar fill | Player profile | Motion spring | 800ms |
| Achievement unlock | On unlock | Lottie / Rive | 1.2s cinematic |
| Explosion particle burst | Interactive elements | Canvas / Three.js | 600ms |
| Leaderboard rank animation | Scores | Motion stagger | 600ms |
| HUD scan-line effect | Overlays | CSS | 3s linear loop |

#### Skip These
- Pixel art loading animation for non-pixel-art games (brand inconsistency)
- Particle explosions on every click (performance killer on mobile)
- Auto-playing video backgrounds without a mute button (WCAG violation)

#### Recommended Stack
**Primary:** GSAP (best for complex gaming-style sequences)  
**For 3D tilt:** Vanilla JS event listeners + CSS transforms (lightest)  
**For achievements:** Rive (stateful, interactive, GPU-accelerated)  
**For particles:** tsParticles or Three.js

#### Starter — 3D Card Tilt (Vanilla JS)
```javascript
document.querySelectorAll('.game-card').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width - 0.5) * 20;
    const y = ((e.clientY - rect.top) / rect.height - 0.5) * -20;
    card.style.transform = `perspective(600px) rotateX(${y}deg) rotateY(${x}deg)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = 'perspective(600px) rotateX(0) rotateY(0)';
    card.style.transition = 'transform 400ms ease-out';
  });
});
```

---

### 📱 13. App Landing Pages

**Tone:** Modern, feature-clear, conversion-focused. Animation explains the app without words.

#### Essential Animations

| Animation | Where | Library | Duration |
|---|---|---|---|
| Phone mockup scroll animation | Hero | Motion scroll | Scroll-linked |
| Feature card floating | Features section | Motion | 3–4s gentle loop |
| App screen carousel | Feature showcase | Embla Carousel | 350ms slide |
| Notification pop | Demo of push notifications | Motion | 400ms spring |
| Download button pulse | CTA | CSS | 1.5s loop |
| Onboarding step slide | How it works | Motion | 400ms |
| Interactive phone tilt | Hero mockup | Vanilla JS + CSS | Real-time |

#### Skip These
- App icon bounce in navigation (navigation should be instant)
- Screen recording mock animation that autoplays with audio
- Gradient blob hero that obscures the app screenshot

#### Recommended Stack
**Primary:** Motion (Framer Motion)  
**For carousels:** Embla Carousel  
**For scroll-linked phone mockup:** Motion `useScroll` + `useTransform`

#### Starter — Phone Scroll Mockup (Motion)
```jsx
import { useScroll, useTransform, motion } from 'motion/react';

const PhoneMockup = () => {
  const { scrollYProgress } = useScroll();
  const y = useTransform(scrollYProgress, [0, 0.3], [0, -80]);
  const rotateX = useTransform(scrollYProgress, [0, 0.3], [20, 0]);

  return (
    <motion.div
      style={{ y, rotateX, transformPerspective: 1000 }}
      className="phone-mockup"
    />
  );
};
```

---

### ⏳ 14. Loading Animations

**The rule:** The best loading animation is the one users never see. Skeleton screens are almost always better than spinners.

#### Hierarchy of Preference

1. **Skeleton screens** — show the shape of content while it loads. Users perceive this as fastest.
2. **Shimmer / shimmer on skeleton** — adds perceived activity to skeleton screens.
3. **Progress bars** — use when you have actual progress data (upload, multi-step).
4. **Spinners** — only for short, unpredictable waits (<3 seconds).
5. **Brand / mascot loaders** — only on initial app load, never on subsequent navigation.

#### Implementations

| Loader Type | Library | Duration | When |
|---|---|---|---|
| Skeleton screen | CSS shimmer | 1.5s linear loop | Data fetching |
| Progress bar | Motion / CSS | Real-time fill | File upload, wizard |
| Circular spinner | CSS | 0.8s linear loop | Short waits |
| Dots wave | CSS stagger | 0.6s + 0.2s stagger | Chat / typing |
| Page transition | Motion / GSAP | 400–600ms | Route changes |
| Initial app loader | Rive / Lottie | 1.5–3s | First load only |

#### Starter — Shimmer Skeleton (CSS)
```css
.skeleton-line {
  height: 16px;
  border-radius: 4px;
  background: linear-gradient(90deg,
    #e2e8f0 0%, #f8fafc 40%, #e2e8f0 80%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
}
@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Dark mode variant */
@media (prefers-color-scheme: dark) {
  .skeleton-line {
    background: linear-gradient(90deg, #1e293b 0%, #334155 40%, #1e293b 80%);
    background-size: 200% 100%;
  }
}
```

#### Starter — Dots Typing Loader (CSS)
```css
.typing-dots span {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: typingDot 0.6s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typingDot {
  0%, 100% { transform: translateY(0); opacity: 0.4; }
  50%       { transform: translateY(-6px); opacity: 1; }
}
```

---

### ✨ 15. Micro-Interactions

These are the details that separate a good UI from a great one. They take 30 minutes each to implement and add months of perceived polish.

#### The Essential 10 (implement all of these on every project)

| Interaction | Trigger | Implementation | Duration |
|---|---|---|---|
| Button hover glow | `:hover` | CSS box-shadow transition | 200ms |
| Button active press | `:active` | `transform: scale(0.96)` | 80ms |
| Input focus ring | `:focus-visible` | CSS outline + glow | 150ms |
| Checkbox / toggle | Click | Motion spring | 200ms |
| Error shake | Invalid submit | CSS translate keyframes | 400ms |
| Success checkmark | Form success | CSS stroke-dashoffset | 500ms draw |
| Copy button confirmation | Click | State swap + Motion | 300ms |
| Accordion expand | Click | Motion height animation | 250ms |
| Tooltip fade | Hover delay | CSS opacity + delay | 150ms in, 100ms out |
| Modal scale-in | Open | Motion scale + backdrop | 300ms |

#### Starter — Button Press + Hover (CSS)
```css
.btn {
  transition: transform 80ms, box-shadow 200ms, background-color 200ms;
}
.btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 25px -4px rgba(99, 102, 241, 0.4);
}
.btn:active {
  transform: translateY(0) scale(0.96);
  box-shadow: 0 2px 8px -2px rgba(99, 102, 241, 0.4);
}
```

#### Starter — Magnetic Button Effect (JS)
```javascript
document.querySelectorAll('.magnetic-btn').forEach(btn => {
  btn.addEventListener('mousemove', (e) => {
    const rect = btn.getBoundingClientRect();
    const x = (e.clientX - rect.left - rect.width / 2) * 0.25;
    const y = (e.clientY - rect.top - rect.height / 2) * 0.25;
    btn.style.transform = `translate(${x}px, ${y}px)`;
  });
  btn.addEventListener('mouseleave', () => {
    btn.style.transform = '';
    btn.style.transition = 'transform 400ms cubic-bezier(0.34, 1.56, 0.64, 1)';
  });
});
```

#### Starter — Input Focus Glow
```css
.input {
  border: 1.5px solid #e2e8f0;
  outline: none;
  transition: border-color 150ms, box-shadow 150ms;
}
.input:focus-visible {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
}
```

---

## 8. 2025 Trend Spotlight

### 🔥 Trend 1 — CSS Scroll-Driven Animations (No JavaScript)

The most important new animation capability in 2025. Runs entirely **off the main thread** — animations can't be blocked by JavaScript or heavy computation. Chrome/Edge support is solid; Safari support landed in 2025.

```css
/* Progress bar that fills as user scrolls */
.scroll-progress {
  position: fixed;
  top: 0; left: 0;
  height: 3px;
  background: #6366f1;
  transform-origin: left;
  animation: progress linear both;
  animation-timeline: scroll(root);
}
@keyframes progress {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}

/* Element that fades in as it enters the viewport */
.reveal-on-scroll {
  animation: revealUp linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 30%;
}
@keyframes revealUp {
  from { opacity: 0; transform: translateY(40px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

Add a `@supports` check for production:
```css
@supports (animation-timeline: scroll()) {
  /* Scroll-driven animation rules */
}
```

### 🔥 Trend 2 — View Transitions API

Native page transition animations with `document.startViewTransition()`. No library needed.

```javascript
// Wrap navigation or DOM updates in a view transition
document.startViewTransition(() => {
  document.getElementById('content').innerHTML = newPageHTML;
});
```

```css
/* The outgoing page */
::view-transition-old(root) {
  animation: 300ms ease-out fadeSlideOut;
}
/* The incoming page */
::view-transition-new(root) {
  animation: 300ms ease-out fadeSlideIn;
}
@keyframes fadeSlideOut {
  to { opacity: 0; transform: translateX(-30px); }
}
@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateX(30px); }
}
```

### 🔥 Trend 3 — Physics-Based Spring Animations

Spring animations (no fixed duration — they naturally decelerate) feel dramatically more real than cubic-bezier easing. Motion and React Spring both support them.

```jsx
// Motion — spring transition
<motion.div
  animate={{ x: isOpen ? 200 : 0 }}
  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
/>

// The three values to know:
// stiffness: how fast it moves (100 = slow, 500 = fast)
// damping:   how much it bounces (10 = lots of bounce, 40 = none)
// mass:      simulated weight (1 = default, higher = heavier feel)
```

### What's Fading Out in 2025

| Trend | Why It's Declining |
|---|---|
| Heavy parallax on every section | Causes motion sickness, hurts mobile perf |
| Cursor trail effects on portfolio sites | Now feels dated (peaked ~2022) |
| Intro / splash screen animations | Users skip them — just kill the loader |
| Auto-playing looping hero videos | High bandwidth, WCAG issues |
| Infinite floating blob backgrounds | Overused to the point of cliché |
| Page scroll hijacking | Always hated, browsers now partially block it |

---

## 9. Implementation Code Patterns

### Pattern A — Motion (Framer Motion) — Reusable FadeIn Component

```jsx
// components/FadeIn.tsx
import { motion, useReducedMotion } from 'motion/react';

interface FadeInProps {
  children: React.ReactNode;
  delay?: number;
  direction?: 'up' | 'down' | 'left' | 'right';
}

const directionMap = {
  up:    { y: 40 },
  down:  { y: -40 },
  left:  { x: 40 },
  right: { x: -40 },
};

export const FadeIn = ({ children, delay = 0, direction = 'up' }: FadeInProps) => {
  const shouldReduce = useReducedMotion();

  return (
    <motion.div
      initial={{ opacity: 0, ...(shouldReduce ? {} : directionMap[direction]) }}
      whileInView={{ opacity: 1, y: 0, x: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{
        duration: 0.6,
        delay,
        ease: [0, 0, 0.2, 1], // Google's "Decelerate" curve
      }}
    >
      {children}
    </motion.div>
  );
};
```

### Pattern B — GSAP with React (useGSAP hook)

```jsx
import { useGSAP } from '@gsap/react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import gsap from 'gsap';

// Register once at module level
gsap.registerPlugin(useGSAP, ScrollTrigger);

const AnimatedSection = () => {
  const containerRef = useRef(null);

  useGSAP(() => {
    // All animations here are automatically cleaned up on unmount
    gsap.from('.card', {
      y: 60,
      opacity: 0,
      duration: 0.6,
      stagger: 0.08,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: containerRef.current,
        start: 'top 80%',
        once: true,
      },
    });
  }, { scope: containerRef });

  return (
    <div ref={containerRef}>
      {cards.map(c => <div key={c.id} className="card">{c.content}</div>)}
    </div>
  );
};
```

### Pattern C — CSS Scroll-Driven (Zero JS)

```css
/* Works in Chrome/Edge + Safari 2025 — add @supports check for Firefox */
@supports (animation-timeline: scroll()) {
  .hero-scale {
    animation: heroZoom linear both;
    animation-timeline: scroll(root);
    animation-range: 0% 40vh;
  }
  @keyframes heroZoom {
    to { transform: scale(1.1); opacity: 0; }
  }
}
```

### Pattern D — Tailwind CSS Custom Animations

```javascript
// tailwind.config.ts
export default {
  theme: {
    extend: {
      keyframes: {
        fadeSlideUp: {
          '0%':   { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        pulse: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(99,102,241,0.4)' },
          '50%':       { boxShadow: '0 0 0 12px rgba(99,102,241,0)' },
        }
      },
      animation: {
        'fade-up':  'fadeSlideUp 0.6s cubic-bezier(0,0,0.2,1) both',
        'shimmer':  'shimmer 1.5s linear infinite',
        'glow':     'pulse 1.5s ease-in-out infinite',
      },
    },
  },
};
```

### Pattern E — React Three Fiber (3D Scene)

```jsx
import { useFrame, useRef } from '@react-three/fiber';
import { Canvas } from '@react-three/fiber';

const SpinningGeometry = () => {
  const meshRef = useRef(null);

  // Runs every frame — keep logic minimal for performance
  useFrame((state, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.4;
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.5) * 0.2;
    }
  });

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1.5, 1]} />
      <meshStandardMaterial color="#6366f1" wireframe />
    </mesh>
  );
};

export const Hero3D = () => (
  <Canvas camera={{ position: [0, 0, 5] }}>
    <ambientLight intensity={0.4} />
    <pointLight position={[10, 10, 10]} />
    <SpinningGeometry />
  </Canvas>
);
```

---

## 10. Quick-Pick Reference Card

### "Which library should I use for ___?"

| Task | Best Choice | Alternative |
|---|---|---|
| React UI transitions | Motion (Framer Motion) | CSS |
| Scroll-triggered sequences | GSAP ScrollTrigger | CSS Scroll-Driven |
| SVG path drawing | GSAP DrawSVG | CSS stroke-dashoffset |
| Interactive animated icons/mascots | Rive | LottieFiles |
| After Effects exports | LottieFiles | Rive |
| 3D / WebGL | React Three Fiber | Three.js (vanilla) |
| Scroll-linked effects (no JS) | CSS Scroll-Driven API | GSAP ScrollTrigger |
| Simple hover/focus states | CSS | — |
| Physics/spring feel | Motion spring | React Spring |
| Lightweight (no React) | Anime.js | CSS |
| Page transitions | Motion / View Transitions API | GSAP |

### "How long should this animation be?"

| Element | Duration |
|---|---|
| Button hover | 150–200ms |
| Dropdown open | 150–250ms |
| Modal enter | 250–350ms |
| Scroll reveal | 400–600ms |
| Page transition | 500–700ms |
| Celebratory effect (confetti, badge) | 800–1500ms |
| Looping background | 4000–10000ms |

### "What easing should I use?"

| Scenario | Easing | CSS |
|---|---|---|
| Element entering screen | Ease out | `cubic-bezier(0, 0, 0.2, 1)` |
| Element leaving screen | Ease in | `cubic-bezier(0.4, 0, 1, 1)` |
| Element moving on screen | Ease in-out | `cubic-bezier(0.4, 0, 0.2, 1)` |
| Springy / playful | Spring overshoot | `cubic-bezier(0.34, 1.56, 0.64, 1)` |
| Progress bars, counters | Linear | `linear` |

---

*Sources: Motion.dev (official docs), GSAP.com, MDN Web Docs, Rive.app, Google Material Design 3, Nielsen Norman Group, Smashing Magazine, LottieFiles.com — all consulted June 2025.*

---

# SaifCraft Site — Animation Playbook

> This chapter is specific to the **SaifCraft portfolio & freelance dev site**. It audits every page for existing animations, maps exactly where new animations should go, and provides ready-to-use code for every recommendation.

**Library already in use:** Framer Motion (`m` from `framer-motion`) + vanilla CSS keyframes + `canvas` (NeuralNetwork). Stick with this stack — do not introduce new libraries.

---

## Audit: What's Already Animated ✅

The site has a strong foundation. Before adding anything, here is exactly what's already working:

| Page / Section | What's animated |
|---|---|
| **Hero** | Neural network canvas (rAF, paused off-screen), blob CSS backgrounds, spring entrance for badge/headline/description, staggered highlight badges, button `whileHover/whileTap` scale, typewriter code effect, animated stat counters |
| **Home — About** | `whileInView` fade-up for profile card, animated skill progress bars (width 0 → %) with stagger |
| **Home — Skills** | `whileInView` slide-in per row, hover border/background on tech badges |
| **Home — Services Preview** | `whileInView` fade-up stagger on cards, hover translate-y lift, group-hover arrow shift |
| **Home — Process** | `whileInView` stagger on all 5 steps, icon `group-hover:scale-110` |
| **Home — Testimonials** | `whileInView` fade-up stagger on cards, hover lift + shadow |
| **Home — Platforms** | `whileInView` stagger, hover lift, arrow bg/color transition |
| **Home — Final CTA** | `whileInView` fade-up |
| **Portfolio page** | `AnimatePresence` for category filter, `animate-pulse` skeleton cards, ProjectCard `whileInView` stagger |
| **ProjectCard** | Image `scale-105` on hover, backdrop-blur overlay fade |
| **Services page** | `fadeUp whileInView` on all cards and rows, `hover:-translate-y-1` lift |
| **About page** | `whileInView` with custom stagger variants, animated progress bars, `animate-ping` available badge, `animate-pulse` dot |
| **Contact page** | `fadeUp` entrance, `focus:ring` on inputs, `animate-spin` submit loader |
| **FAQ page** | `AnimatePresence` accordion height animation |

---

## Audit: What's Missing 🔴

These are the gaps — ranked by impact on perceived quality.

### 🔴 HIGH PRIORITY — Biggest visible gaps

| # | Location | What's missing | Why it matters |
|---|---|---|---|
| 1 | **Header (global)** | No shadow/blur on scroll | Without it, the header feels "glued" — a scroll-based shadow makes the page feel dimensional |
| 2 | **Contact form — success state** | Form submits, but no visual celebration | First time a client makes contact is the highest-emotion moment on the site |
| 3 | **Testimonial stars** | Stars appear instantly, all at once | A staggered fill-in makes the 5-star rating feel earned and credible |
| 4 | **Chatbot button** | Floating button has no attention animation | It blends in — a subtle pulse would increase engagement by 20–40% |
| 5 | **Process timeline connector** | The `h-px` line is static | Animating the connector drawing left-to-right as user scrolls makes the process feel sequential |

### 🟡 MEDIUM PRIORITY — Polish upgrades

| # | Location | What's missing | Why it matters |
|---|---|---|---|
| 6 | **Hero CTA buttons** | No pulsing glow on primary button | "Share Your Idea" is the #1 conversion action — draw the eye |
| 7 | **"Most Popular" badge** | Static label on Custom Web App card | A subtle pulse signals active recommendation |
| 8 | **Portfolio filter tabs** | Active indicator jumps vs slides | A `layoutId` sliding pill feels dramatically more polished |
| 9 | **Dark mode toggle (Header)** | No rotation/morph animation | Sun ↔ Moon transition is a micro-interaction users notice and remember |
| 10 | **Project detail page** | Outcome stats are plain text | Animated count-up on the metrics ("+22% conversions") reinforces social proof |

### 🟢 LOW PRIORITY — Nice-to-have

| # | Location | What's missing |
|---|---|---|
| 11 | **Page route transitions** | No cross-page fade — pages snap in instantly |
| 12 | **Services page — process stepper** | Steps are static, icons have no entrance sequence |
| 13 | **Footer** | Completely static |
| 14 | **404 page** | Static |

---

## Site-Wide Animation Map

Use this as your implementation checklist. Work top-to-bottom.

```
SaifCraft Site
│
├── 🌐 GLOBAL
│   ├── Header — ADD: scroll-shadow effect                          [Priority 1]
│   ├── Header — ADD: dark mode toggle rotation                     [Priority 9]
│   └── Chatbot button — ADD: attention pulse ring                  [Priority 4]
│
├── 🏠 HOME PAGE (/)
│   ├── Hero — ✅ Done (Neural net, counters, typewriter, springs)
│   ├── About inline — ✅ Done (progress bars, whileInView)
│   ├── Skills — ✅ Done (slide-in rows)
│   ├── Projects gallery — ✅ Done (ProjectCard stagger)
│   ├── Services preview — ✅ Done (stagger, hover lift)
│   │   └── "Most Popular" badge — ADD: subtle pulse                [Priority 7]
│   ├── Process steps — ✅ Done (stagger)
│   │   └── Connector line — ADD: draw animation                    [Priority 5]
│   ├── Testimonials — ✅ Done (stagger, hover)
│   │   └── Star ratings — ADD: staggered pop-in                    [Priority 3]
│   ├── Platforms — ✅ Done
│   └── CTA section — ADD: primary button glow pulse                [Priority 6]
│
├── 💼 PORTFOLIO (/portfolio)
│   ├── Hero — ✅ Done (whileInView)
│   ├── Filter tabs — ADD: layoutId sliding indicator               [Priority 8]
│   ├── Project grid — ✅ Done (stagger, skeleton)
│   └── ProjectCard — ✅ Done (image scale, overlay)
│
├── 📋 PORTFOLIO DETAIL (/portfolio/:id)
│   ├── Header — no animation (acceptable)
│   └── Outcome stats — ADD: count-up on scroll                     [Priority 10]
│
├── 🛠 SERVICES (/services)
│   ├── Hero — ✅ Done
│   ├── Pricing cards — ✅ Done
│   └── Process stepper — ADD: step icon entrance stagger           [Priority 12]
│
├── 👤 ABOUT (/about)
│   ├── Hero — ✅ Done (ping badge, progress bars)
│   ├── Pillars — ✅ Done (whileInView variants)
│   └── Timeline — ✅ Done (whileInView stagger)
│
├── 📬 CONTACT (/contact)
│   ├── Hero — ✅ Done
│   ├── Form — ✅ Done (focus rings, spin loader)
│   └── Success state — ADD: checkmark + confetti burst             [Priority 2]
│
└── ❓ FAQ (/faq)
    ├── Hero — ✅ Done
    └── Accordion — ✅ Done (AnimatePresence height)
```

---

## Ready-to-Use Code for Every Priority

### Priority 1 — Header Scroll Shadow

Add to `src/components/layout/Header.tsx`. No new library needed — one `useEffect`.

```tsx
// At the top of the Header component
const [scrolled, setScrolled] = useState(false);

useEffect(() => {
  const onScroll = () => setScrolled(window.scrollY > 8);
  window.addEventListener('scroll', onScroll, { passive: true });
  return () => window.removeEventListener('scroll', onScroll);
}, []);

// On the header element, replace the static className with:
<header
  className={`sticky top-0 z-50 w-full border-b transition-all duration-300 ${
    scrolled
      ? 'border-border bg-background/95 backdrop-blur-md shadow-sm shadow-black/5'
      : 'border-transparent bg-background/80 backdrop-blur-sm'
  }`}
>
```

---

### Priority 2 — Contact Form Success Animation

Add to `src/features/contact/components/ContactForm.tsx`. Fires after successful Firestore write.

```tsx
import { m, AnimatePresence } from 'framer-motion';

// Replace the existing success state render with:
<AnimatePresence>
  {isSuccess && (
    <m.div
      initial={{ opacity: 0, scale: 0.85, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ type: 'spring', stiffness: 260, damping: 22 }}
      className="flex flex-col items-center gap-4 py-12 text-center"
    >
      {/* Animated checkmark circle */}
      <m.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.1, type: 'spring', stiffness: 300, damping: 18 }}
        className="w-16 h-16 rounded-full bg-emerald-500/15 border-2 border-emerald-500 flex items-center justify-center"
      >
        <m.svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-8 h-8 text-emerald-500"
        >
          <m.path
            d="M5 13l4 4L19 7"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ delay: 0.3, duration: 0.5, ease: 'easeOut' }}
          />
        </m.svg>
      </m.div>

      <m.h3
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="text-xl font-display font-bold text-foreground"
      >
        Message Sent!
      </m.h3>
      <m.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="text-sm text-muted-foreground max-w-xs"
      >
        Saif typically replies within a few hours. Check your inbox — you'll hear back soon.
      </m.p>
    </m.div>
  )}
</AnimatePresence>
```

---

### Priority 3 — Testimonial Stars Stagger Pop-In

In `src/features/home/pages/Home.tsx`, inside the testimonial card's stars row:

```tsx
// Replace the static star render:
<div className="flex gap-0.5">
  {Array.from({ length: t.stars }).map((_, s) => (
    <m.div
      key={s}
      initial={{ opacity: 0, scale: 0, rotate: -20 }}
      whileInView={{ opacity: 1, scale: 1, rotate: 0 }}
      viewport={{ once: true }}
      transition={{
        delay: i * 0.1 + s * 0.07,   // card delay + star delay
        type: 'spring',
        stiffness: 300,
        damping: 15,
      }}
    >
      <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
    </m.div>
  ))}
</div>
```

---

### Priority 4 — Chatbot Button Attention Pulse

In `src/features/chatbot/components/ChatBot.tsx`, wrap the trigger button:

```tsx
// Add a pulse ring that fires every 5 seconds to draw attention
<div className="relative">
  {/* Pulse ring — only visible when chat is closed */}
  {!isOpen && (
    <m.div
      className="absolute inset-0 rounded-full bg-primary"
      animate={{ scale: [1, 1.5, 1.5], opacity: [0.4, 0, 0] }}
      transition={{ duration: 2, repeat: Infinity, repeatDelay: 3 }}
    />
  )}
  {/* Existing button */}
  <button className="relative w-12 h-12 rounded-full bg-primary ...">
    {/* existing icon */}
  </button>
</div>
```

---

### Priority 5 — Process Timeline Connector Draw

In `src/features/home/pages/Home.tsx`, replace the static `h-px` connector line:

```tsx
// Replace:
// <div className="hidden lg:block absolute top-[2.6rem] left-[10%] right-[10%] h-px bg-border z-0" />

// With:
<div className="hidden lg:block absolute top-[2.6rem] left-[10%] right-[10%] h-px bg-border/30 z-0 overflow-hidden">
  <m.div
    className="h-full bg-primary/40 origin-left"
    initial={{ scaleX: 0 }}
    whileInView={{ scaleX: 1 }}
    viewport={{ once: true, amount: 0.5 }}
    transition={{ duration: 1.2, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
  />
</div>
```

---

### Priority 6 — Hero CTA Glow Pulse

In `src/features/home/components/Hero.tsx`, add a pulsing ring behind the primary button:

```css
/* In src/index.css */
@keyframes ctaGlow {
  0%, 100% { box-shadow: 0 0 0 0 hsl(var(--primary) / 0.45); }
  50%       { box-shadow: 0 0 0 10px hsl(var(--primary) / 0); }
}
.btn-cta {
  animation: ctaGlow 2s ease-in-out infinite;
}
```

The `btn-cta` class is already on the button. Just add the keyframe — no JSX change needed.

---

### Priority 7 — "Most Popular" Badge Pulse

In `src/features/home/pages/Home.tsx`, find the `Most Popular` badge span:

```tsx
// Replace the static span with:
<span className="bg-primary text-primary-foreground text-[11px] font-bold px-2.5 py-1 rounded-full flex items-center gap-1 relative">
  <m.span
    className="absolute inset-0 rounded-full bg-primary"
    animate={{ scale: [1, 1.25], opacity: [0.4, 0] }}
    transition={{ duration: 1.5, repeat: Infinity, ease: 'easeOut' }}
  />
  <Star className="w-3 h-3 fill-current relative z-10" />
  <span className="relative z-10">Most Popular</span>
</span>
```

---

### Priority 8 — Portfolio Filter Sliding Indicator

In `src/features/portfolio/pages/Portfolio.tsx`, the category filter buttons:

```tsx
// Add layoutId to a shared indicator behind the active button
{categories.map((cat) => (
  <button
    key={cat}
    onClick={() => setActiveCategory(cat)}
    className={`relative flex-shrink-0 h-10 px-4 rounded-full text-xs sm:text-sm font-semibold border transition-colors duration-200 ${
      activeCategory === cat
        ? 'bg-primary text-primary-foreground border-primary'
        : 'bg-card text-muted-foreground border-border hover:border-primary/40 hover:text-foreground'
    }`}
  >
    {/* Sliding background pill */}
    {activeCategory === cat && (
      <m.div
        layoutId="filter-pill"
        className="absolute inset-0 rounded-full bg-primary -z-10"
        transition={{ type: 'spring', stiffness: 350, damping: 30 }}
      />
    )}
    <span className="relative z-10">{cat}</span>
  </button>
))}
```

> **Note:** Remove `bg-primary` from the button className when using layoutId — the pill provides the background.

---

### Priority 9 — Dark Mode Toggle Rotation

In `src/components/layout/Header.tsx`, wrap the toggle icon:

```tsx
import { m } from 'framer-motion';

// Wrap each icon (Sun/Moon) in a motion.div:
<m.div
  key={isDark ? 'moon' : 'sun'}
  initial={{ rotate: -90, opacity: 0 }}
  animate={{ rotate: 0, opacity: 1 }}
  exit={{ rotate: 90, opacity: 0 }}
  transition={{ duration: 0.2 }}
>
  {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
</m.div>

// Wrap in AnimatePresence:
<AnimatePresence mode="wait">
  {/* motion.div above */}
</AnimatePresence>
```

---

### Priority 10 — Project Detail Outcome Stats Count-Up

In `src/features/portfolio/pages/ProjectDetail.tsx`, for numeric outcome stats:

```tsx
import { useMotionValue, useSpring, useTransform, useInView, m } from 'framer-motion';
import { useRef, useEffect } from 'react';

function AnimatedStat({ value, label }: { value: string; label: string }) {
  // Extract numeric part — e.g. "+22%" → 22
  const num = parseFloat(value.replace(/[^0-9.]/g, ''));
  const prefix = value.match(/^[^0-9]*/)?.[0] ?? '';
  const suffix = value.match(/[^0-9.]*$/)?.[0] ?? '';

  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const raw = useMotionValue(0);
  const spring = useSpring(raw, { stiffness: 60, damping: 18 });
  const display = useTransform(spring, v => `${prefix}${Math.round(v)}${suffix}`);

  useEffect(() => { if (inView) raw.set(num); }, [inView, num]);

  return (
    <div ref={ref} className="text-center">
      <m.p className="text-2xl font-display font-bold text-foreground">{display}</m.p>
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
    </div>
  );
}
```

---

## Final Priority Checklist

Copy this into your task list — implement in order:

```
[ ] 1. Header scroll shadow (10 min — pure CSS class toggle)
[ ] 2. Contact form success checkmark animation (20 min)
[ ] 3. Testimonial star stagger pop-in (10 min)
[ ] 4. Chatbot button pulse ring (10 min)
[ ] 5. Process connector line draw (5 min)
[ ] 6. Hero CTA glow pulse — add @keyframes to index.css (5 min)
[ ] 7. "Most Popular" badge pulse (10 min)
[ ] 8. Portfolio filter sliding pill indicator (15 min)
[ ] 9. Dark mode toggle rotation (10 min)
[ ] 10. Project detail outcome stats count-up (20 min)
```

**Total estimated time: ~2 hours** to implement all 10 improvements and transform the site from "well-animated" to "exceptionally polished."

---

## What NOT to Add on This Site

Avoid these — they would hurt more than help:

| Animation | Reason to skip |
|---|---|
| Scroll hijacking / custom scroll speed | Breaks expected behaviour; harms UX on long service/about pages |
| Heavy 3D scene on Services or About page | Neural network canvas on Hero is already the 3D statement — doubling up adds noise |
| Parallax on every section | Causes motion sickness on mobile; the site already has depth from blob backgrounds |
| Auto-playing looping text / marquee | Text marquees on a dev portfolio signal "no white space left" — you have good copy, let it breathe |
| Page transition wipe/slide | Route transitions add 300–500ms of delay between pages; the fast navigation is a feature |
| Cursor trail | Was trendy in 2022; now signals "template" more than craft |
