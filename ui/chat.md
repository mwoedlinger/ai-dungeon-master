⏺ The redesign is complete. Here's a summary of what changed:

  Color & Atmosphere
  - Deeper, richer dark palette (#0d0f1a base vs old #1a1a2e) with warm undertones
  - Subtle noise texture overlay for visual depth
  - Ambient radial gradient glows (magic purple, teal, gold) on the background
  - Vignette effects on the title screen

  Typography
  - Cinzel + Cinzel Decorative display fonts for all headings, labels, and UI chrome — an ornate serif that reads as medieval/fantasy
  - Drop caps on narrative prose openings (first paragraph gets a large decorative initial letter in gold)
  - Better typographic hierarchy with tracking-wider, uppercase small labels

  Title Screen
  - Floating ambient glow orbs with pulsing animation
  - Ornate decorative rules (gold ✦ and ◆ ◆ ◆ dividers)
  - Cinzel Decorative titling with gold text-shadow glow
  - Loading spinner, atmospheric tagline, flavor quote

  Visual Effects
  - ornate-border class: gold corner brackets on modals
  - corner-accents class: subtle gold corner marks on character cards
  - glow-* / text-glow-* utility classes for subtle element glow
  - divider-ornate: gradient line with centered diamond ornament
  - Custom btn-primary and btn-ghost with gradient backgrounds and glow hover states
  - card class with gradient surface and hover elevation

  Animations
  - slide-up, slide-in-right, fade-in-slow for modals/drawers
  - combat-pulse for combat overlay border breathing
  - float for the idle-state sword icon
  - pulse-glow for ambient orbs and streaming indicator
  - shimmer for potential loading states

  Components
  - Header: slim with gold accent line, time icons, diamond separators
  - Narrative: top/bottom gradient fades, larger padding, atmospheric empty state
  - Prose: drop caps, deeper text shadows
  - Player input bubbles: gradient teal tint with subtle glow
  - Mechanical events: refined color hierarchy, wrapper component for crits/spells
  - Combat overlay: gradient background with pulsing danger border glow
  - Character cards: gradient card surface, corner accents, display font names
  - Character sheet modal: ornate border corners, backdrop blur, section headers with gold display font
  - Inventory drawer: slide-in animation, extracted InventoryItem component
  - Sidebar tabs: icons above labels, accent glow indicator line
  - HP bars: gradient fills with color-matched glow shadows
  - Spell slot pips: glow on available slots
  - Condition badges: semi-transparent backgrounds with subtle glow per condition
  - Quick actions: icons + uppercase display font labels
