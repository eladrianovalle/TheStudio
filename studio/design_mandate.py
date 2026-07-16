#!/usr/bin/env python3
"""
Design-phase critique guide: the anti-slop blacklist, the embarrassment
self-gate, the anti-convergence directive, and the Goodwill Reservoir.

DESIGN_CRITIQUE_GUIDE mirrors CONTRARIAN_MANDATE in scopes.py — a list of
markdown lines injected into a prompt. It is gated to the DESIGN phase only
(see run_phase.build_instruction_doc), because these checks are specific to
game UI, HUDs, menus, and store/marketing pages, not to market or tech work.

Borrowed from gstack's design skills (R6 + R7) and adapted for games.
"""
from __future__ import annotations


# The blacklist, the self-gate, the anti-convergence directive, and the
# Goodwill Reservoir. Injected into the DESIGN phase's Agent Roles section
# so both the advocate and the contrarian design against it.
DESIGN_CRITIQUE_GUIDE = [
    "## Design Critique Guide (design phase)",
    "",
    "This phase produces UI, HUDs, menus, and store/marketing pages. Those are exactly where generated design collapses into the same handful of safe defaults. The checks below exist to catch that collapse — apply them to every screen you propose and every screen you critique.",
    "",
    "### AI-slop blacklist — reject these on sight",
    "",
    "Each of these is what output looks like when nobody made a real choice. Treat any of them as a defect to fix, not a style to defend. Name the specific offender and say what to do instead.",
    "",
    "1. **The default dark purple-to-blue gradient backdrop.** Every menu, splash, and store hero drifts toward the same sci-fi/fantasy gradient. Pick a backdrop that comes from *this* game's world.",
    "2. **The three-panel layout by reflex.** Three evenly-spaced cards or stat panels (Play / Options / Quit, or three identical feature boxes) because three fills the row. Lay out by what the player actually reaches for first, not by the grid.",
    "3. **Ability and stat icons dropped in flat colored circles.** The circle adds nothing and flattens every icon into the same shape. Let the icon carry the read, or give the frame a reason to exist.",
    "4. **Everything centered, nothing anchored.** HUD and menu elements floated dead-center with nothing tied to the screen edges. Real HUDs anchor to corners and edges so the center stays clear for play.",
    "5. **One bubbly corner radius on every surface.** The same rounded rectangle on buttons, panels, cards, and portraits. Corner shape is a voice — a gritty game and a cozy game should not round their edges the same way.",
    "6. **Floating particles, bokeh, and glow orbs as filler.** Decorative motion sprinkled on to look 'polished' while saying nothing about the game. Cut it, or make it read as something in the world.",
    "7. **Emoji standing in for real icons.** A heart for health, a star for score, a coin emoji for currency. It reads as placeholder art that shipped. Use real icons made for the game.",
    "8. **The colored left-stripe card.** Quest logs, item tooltips, and patch notes all wearing the same accent bar down the left edge. It is a web-dashboard tell, not a game surface.",
    "9. **Hero copy that could sell any game.** 'Embark on an epic adventure,' 'Unleash your power,' 'The ultimate experience.' If the line survives being pasted onto a competitor's page, it says nothing. Write the specific promise this game makes.",
    "10. **The cookie-cutter store page.** Hero image, three feature blurbs, trailer, wishlist button, in that order, indistinguishable from every other page in the tab. Order the page around what makes *this* game worth a look.",
    "11. **Shipping the system font as the display face.** system-ui, -apple-system, or Arial on the title and HUD is 'I gave up on typography.' A game's title and interface type are part of its identity — choose them.",
    "",
    "### The embarrassment self-gate",
    "",
    "Before you call a screen done, ask plainly: **would a designer who cares about this craft be embarrassed to ship this?** If a real player screenshotted it, would it look designed, or generated? If the honest answer is 'generated,' it is not done — say which of the offenses above it is committing and fix that one first.",
    "",
    "### Anti-convergence directive",
    "",
    "Left alone, every generation slides toward the same safe look. Push against it on purpose. **Name the default that everything converges on for this kind of screen — then deliberately do not ship it.** Vary the layout, the type, the color, and the mood across proposals so the options are genuinely different bets, not one idea in three coats of paint. When two proposals look interchangeable, that is a finding: one of them is redundant.",
    "",
    "### The Goodwill Reservoir — score the UX, don't just vibe it",
    "",
    "Taste is easier to argue about when it is a number. Every design deliverable carries a **Goodwill Reservoir**: a running UX score that makes 'this respects the player' and 'this abuses the player' legible.",
    "",
    "- **Start at 70 out of 100.** A competent, unremarkable design that neither delights nor offends sits here. You move from 70 by what the design actually does to the player.",
    "- **Dock points for player-hostile choices:**",
    "  - Hiding what the player needs to decide — real cost of a purchase, what a bundle contains, how to reach support.",
    "  - Punishing honest input — rejecting a name, save, or search because of spacing or capitalization the game could have accepted.",
    "  - Forcing unskippable tutorials, logos, or interstitials in front of someone who just wants to play.",
    "  - Dark-pattern monetization — countdown pressure, confusing currencies, a store that nudges the mis-tap toward a buy.",
    "  - Ambiguous choices — a prompt where the player cannot tell what a button will do before pressing it.",
    "  - A sloppy surface — misaligned elements, clashing type, or any blacklist offense above.",
    "- **Credit points for player-respecting choices:**",
    "  - The top task is obvious and reachable — resume play, the main action, the way out.",
    "  - Costs and consequences shown up front, before commitment, in plain terms.",
    "  - Steps removed — a sane default, a remembered choice, one fewer confirmation to clear.",
    "  - Graceful recovery — a wrong turn, dropped connection, or failed input the player can undo or retry without losing progress.",
    "- **Report the score with its ledger.** Give the final number and the specific debits and credits that produced it, so the score is arguable line by line instead of a gut call. A number the reader cannot audit is worth no more than the vibe it replaced.",
]
