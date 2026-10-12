# Offline AS3 frame-budget feasibility probe

This is an experimental dummy workload, not Better Gwent production code or an
ISMCTS search. No game files, saves or installation were changed by the build.

Original sources: `as3/GwaiFrameBudgetProbe.as`, `as3/gwai_search_probe.ws`.
Build: `python3 tools/feasibility/build_frame_probe.py` from the repository root.
The builder adds one original internal class to the existing AI script pack with
FFDec, verifies that the new class can be exported from the resulting SWF, and
packages the private generated resources under
`mod/feasibility/frame-probe/modGwentAIFrameProbe/`.

The AI's decision-start hook attaches an ENTER_FRAME listener to the Gwent menu.
Each frame runs at most 512 arithmetic iterations, checking a two-millisecond
cooperative deadline every sixteen iterations. After ten seconds it detaches and
resets its private checksum for each measurement. Metrics are explicitly converted
to signed integers matching the WitcherScript event; the checksum preserves its
32-bit pattern as a signed integer. Closing/removing the menu from
the stage cancels an incomplete measurement, detaches both listeners and releases
the host; reopening can start a fresh measurement. A completed measurement
reports iterations, elapsed milliseconds, frames, maximum batch duration, checksum
and iterations/second through a new original WitcherScript event. Another AI turn
can start another measurement. It does not postpone the native AI decision or inspect
cards, deck contents, draw order, saves, rules or the game RNG.

Metrics use `[GwaiSearchProbe]` in the game user-settings file. The WS event saves
user settings and displays a notification. The measured rate is arithmetic-workload
throughput, **not simulated Gwent positions or ISMCTS iterations per second**.
Frame timing is quantized; it is not a hard real-time guarantee. Low fixed iteration
caps can make throughput frame-rate-limited. Actual runtime speed and notification/
event compatibility remain unverified. AS3 compiled offline; WS engine compilation
and in-game acceptance remain in-game checks.

## In-game test checklist — approval and backups first

I decide whether/when to install the offline package. Before installation,
finish/cancel any wager/match, save outside Gwent, exit, and back up saves, user
settings and affected mod files. This probe replaces the same Gwent SWF resource as
the recorder; it must not be blindly stacked with another Gwent SWF replacement.
Review the installed recorder/mod priority and preserve its files for restoration.
No automatic installation command is provided or executed.

When I test an approved installation, confirm the new WS event compiles,
play normally for at least ten seconds after the NPC's first decision, and check the
notification and `[GwaiSearchProbe]` fields. Also close the menu before ten seconds,
reopen and trigger another NPC turn: the canceled measurement should not report,
and the fresh measurement should finish once without duplicate callbacks. Repeated
measurements reset their checksum seed. These lifecycle checks have not been run
in-game. Record frame cap/FPS, hardware, observed
responsiveness, maximum batch milliseconds and iterations/second. Keep this test
separate from recorder/replay collection. Restore the recorder/previous resources
from backups afterwards and remove only this probe's files. These are instructions
for a future in-game test, not claims that those acceptance checks passed.

All generated game-derived SWFs/bundles, manifests and this local feasibility source
remain ignored by the public allowlist. Do not publish extracted/patched native AS.

## Latest offline verification — 2026-10-09

The revised class compiles through FFDec and exports successfully. The builder
also re-exports AIPlayerController to verify exactly one decision-start attachment,
checks that the compiled probe contains listener cleanup, verifies that its native
source SWF was unchanged, and records SHA-256 hashes for all package files. See
`game/feasibility/frame-probe/manifest.json`. This is a static/compile check of AS3,
not a Flash event-lifecycle test or a WitcherScript engine compilation.
