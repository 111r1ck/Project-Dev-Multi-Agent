---
name: Emerald Intelligence
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#bbcabf'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#86948a'
  outline-variant: '#3c4a42'
  surface-tint: '#4edea3'
  primary: '#4edea3'
  on-primary: '#003824'
  primary-container: '#10b981'
  on-primary-container: '#00422b'
  inverse-primary: '#006c49'
  secondary: '#95d3ba'
  on-secondary: '#003829'
  secondary-container: '#0b513d'
  on-secondary-container: '#83c2a9'
  tertiary: '#45dfa4'
  on-tertiary: '#003825'
  tertiary-container: '#00b982'
  on-tertiary-container: '#00422c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#6ffbbe'
  primary-fixed-dim: '#4edea3'
  on-primary-fixed: '#002113'
  on-primary-fixed-variant: '#005236'
  secondary-fixed: '#b0f0d6'
  secondary-fixed-dim: '#95d3ba'
  on-secondary-fixed: '#002117'
  on-secondary-fixed-variant: '#0b513d'
  tertiary-fixed: '#68fcbf'
  tertiary-fixed-dim: '#45dfa4'
  on-tertiary-fixed: '#002114'
  on-tertiary-fixed-variant: '#005137'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  label-caps:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1.0'
    letterSpacing: 0.05em
  code-sm:
    fontFamily: monospace
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 48px
  container-margin: 32px
  gutter: 20px
---

## Brand & Style

This design system is engineered for high-performance AI agent management, evoking a sense of precision, computational power, and refined technical sophistication. The aesthetic bridges the gap between **Modern Corporate** and **Glassmorphism**, utilizing semi-transparent surfaces to imply depth and complexity without sacrificing professional clarity. 

The personality is "High-Tech Orchestrator": authoritative and efficient, yet accessible. It targets developers and system architects who require a calm environment to monitor complex, high-velocity data flows. The emotional response is one of controlled mastery—turning chaotic JSON logs and agent chains into a streamlined, tactile experience.

## Colors

The palette is anchored by a sophisticated **Deep Emerald** primary accent. In dark mode, the background utilizes a deep "Midnight Navy" (#020617) to provide more depth than pure black, allowing the emerald highlights to vibrate with a high-tech energy. 

- **Primary Emerald (#10B981):** Used for active states, primary action buttons, and successful agent status indicators.
- **Surface Tints:** Use secondary emerald shades for low-priority backgrounds or subtle hover states.
- **Data Visualization:** For JSON and logs, use high-contrast emerald and mint tones against a near-black code block background to ensure legibility.
- **Accents:** Use success (emerald), warning (amber), and error (rose) sparingly, ensuring they are calibrated to the dark theme's saturation levels.

## Typography

This design system utilizes **Inter** for its neutral, systematic reliability across UI elements and body copy. To inject a technical edge, **Space Grotesk** is introduced for labels and metadata, providing a geometric, futuristic contrast.

- **Hierarchical Contrast:** Use bold weights for agent names and status titles.
- **Monospaced Content:** All JSON data, logs, and shell outputs must use a monospace font (system default or JetBrains Mono) at a slightly smaller scale (14px) to maximize information density.
- **Readability:** Maintain generous line height (1.6) for agent descriptions to prevent visual fatigue during long monitoring sessions.

## Layout & Spacing

The layout follows a **Fluid Grid** model with a sidebar-heavy architecture common in complex dashboards. 

- **Grid System:** A 12-column grid is used for the main content area. Components like "Agent Health" or "Live Logs" typically span 4 or 8 columns.
- **Rhythm:** An 8px base unit (4px for micro-adjustments) ensures mathematical consistency.
- **Information Density:** Use "Tight" spacing (8px-12px) within data-heavy cards and "Loose" spacing (24px-32px) between major functional sections to allow the eye to rest.
- **Sidebars:** The left navigation is fixed at 280px, while the right "Inspector" panel for JSON data is collapsible and fluid between 300px and 500px.

## Elevation & Depth

This design system uses **Glassmorphism** and **Tonal Layering** to create a distinct hierarchy of information.

- **Base Layer:** The deepest navy background.
- **Surface Layer:** Subtle glassmorphic cards with a 1px border (color: white, opacity: 0.1) and a backdrop-filter blur of 12px. This creates a "frosted" effect that separates agent cards from the background.
- **Floating Layer:** Modals and tooltips utilize a more opaque background with an ambient emerald-tinted shadow (0px 20px 50px rgba(0, 0, 0, 0.5)) to simulate physical distance from the dashboard surface.
- **Active State:** Elements being dragged or currently "processing" should glow slightly using an outer shadow with the primary emerald color at 20% opacity.

## Shapes

The shape language is modern and approachable. A **roundedness level of 2** (0.5rem / 8px base) is applied to most UI components, with larger containers like dashboard cards utilizing **rounded-xl** (1.5rem / 24px) to emphasize the "glass tile" aesthetic.

- **Buttons:** Fully pill-shaped (rounded-full) for primary actions to distinguish them from the rectangular layout of the grid.
- **Input Fields:** 12px corner radius to match the card interior's aesthetic.
- **Status Indicators:** Small 4px radius squares or perfect circles for "running/stopped" indicators.

## Components

- **Glass Cards:** The primary container. Must include a `backdrop-filter: blur(12px)`, a subtle 1px border, and a 12px-24px internal padding.
- **Primary Buttons:** Solid emerald fill with white text. On hover, apply a subtle glow effect (`box-shadow: 0 0 15px rgba(16, 185, 129, 0.4)`).
- **Status Chips:** High-contrast capsules. "Running" uses a pulsing emerald dot; "Idle" uses a muted slate; "Error" uses a sharp rose tint.
- **JSON Inspector:** A specialized component with syntax highlighting, "copy to clipboard" functionality on hover, and a dark, recessed background (#0B0F1A) to differentiate it from standard UI cards.
- **Agent Logs:** A scrolling vertical list with timestamped entries. Timestamps should be in Space Grotesk and muted (50% opacity) to prioritize the log message.
- **Workflow Nodes:** Connected elements in the management view should use "pipes" that glow emerald when data is flowing through them.