# MailTube design system

The accepted desktop concept is `mailtube-dashboard-concept.png` at 1536×1024.

## Direction

MailTube is a bright editorial media console: an open split canvas rather than a grid of cards. The conversion workbench owns roughly three fifths of the viewport and the live queue is a ruled rail. The layout becomes a single column below tablet width.

## Tokens

- Paper: `#f7f4ec`
- Paper raised: `#fffdf8`
- Ink: `#12120f`
- Muted ink: `#5d5b55`
- Rule: `#b8b5ad`
- Cobalt: `#0757ee`
- Cobalt hover: `#0447c7`
- Vermilion: `#e83b1d`
- Ready: `#247a3a`
- Radius: 3px controls, 6px large input, no decorative pill geometry
- Shadow: none for normal surfaces; focus and transient overlays only

## Type

- Display and product mark: Fraunces, 600, tight tracking.
- Interface, body and control chrome: IBM Plex Sans, 400–600.
- Monospace values and URL input: IBM Plex Mono.
- Main heading: responsive 56–84px, line-height 0.98.
- UI labels: 13–15px, medium weight; body copy: 17–22px.

## Components

- Header: quiet wordmark, four text destinations, one outlined admin control.
- Workbench: large textarea, ruled format and quality ToggleGroups, disclosure row, cobalt primary button.
- Queue: open numbered rows separated by rules; no row cards.
- Status: text plus a thin progress rule. Vermilion is active/error, green is ready.
- Notices: icon, headline and one line of copy behind a top rule.
- Overlays: shadcn Drawer/Dialog using the same square editorial geometry.

## Motion

- 160–220ms ease-out for selection and hover.
- Progress width transitions only; no looping decorative animation.
- New queue rows reveal with a short opacity/translate transition.
- All motion disabled through `prefers-reduced-motion`.

