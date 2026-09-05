# Recurring defects

Fleet-wide record of defects that have bitten more than once across projects, with the real cause
and the fix, so the next person spends minutes not hours. If you burn time rediscovering something
that turns out to be "we have hit this before," add it here.

One entry per defect. Keep it concrete: the observable symptom, the true cause, the fix, how to spot
it fast, and why it was hard to catch. Newest first.

---

## Flutter: two yellow lines under text ("missing Material ancestor" fallback)

**Stacks:** every Flutter app in the fleet (Melisae, and by extension Numaka, Chinara, Sporcelium,
ai-hub-android, storytime, any future Flutter surface).

**Symptom:** a line of text shows **two faint yellow horizontal lines under it** (a yellow double
underline). Often reported as "two little yellow lines" near a footer or pinned element. Tends to be
**one platform only** (e.g. mobile/narrow web but not desktop), which sends people hunting for a
platform-specific styling bug.

**Cause:** it is not a divider, border, or design element. It is Flutter's **missing-`Material`
fallback text style**. A `Text` (or icon) rendered with **no `Material` (or `DefaultTextStyle`)
ancestor** is drawn with a yellow double underline as a built-in "you forgot a Material" signal. It
renders in **release too**, and CanvasKit (web) shows it. Classic triggers: a widget pinned OUTSIDE
a page's `Scaffold` (an app shell, overlay, banner, custom chrome) whose wrapper is a bare
`ColoredBox` / `Container` / `DecoratedBox` instead of a `Material`/`Scaffold`.

**Fix:** give the text a `Material` ancestor. Simplest is to make the wrapper a `Material` instead of
a bare box, e.g. `Material(color: <bg>, child: ...)` in place of `ColoredBox(color: <bg>, ...)`.
Belt-and-suspenders: set `decoration: TextDecoration.none` on the offending `Text` style. A
platform split in the symptom usually means one shell branch already has a `Material`/`Scaffold` and
the other does not, fix the branch that uses the bare box.

**How to spot it fast:** if you see two yellow lines under text, grep the shared shell/chrome for a
`ColoredBox` / `Container` / `DecoratedBox` that wraps a `Text` or a pinned mark with no
`Material`/`Scaffold` above it. It will be common to "every screen," so look in the app shell, not
the individual screens.

**Why it is hard to catch here:** it cannot be reproduced in the FORGE sandbox. Headless Chromium
will not paint CanvasKit (no GPU), and the `flutter_test` rasterizer SUPPLIES a default text style
that SUPPRESSES this exact fallback, so widget and golden captures do not show it. Trust the
mechanism and the platform split; do not wait for a local screenshot to confirm.

**History:** hit repeatedly. Most recent: Melisae ISTL footer, mobile web, fixed 2026-09-05 (the
mobile `_appShell` branch wrapped the pinned mark in a `ColoredBox`; desktop used a `Scaffold`, hence
mobile-only). Two dead ends first blamed an amber hexagon tick in the same mark and removed it, the
lines stayed, because the underline is on the text from the missing Material.
