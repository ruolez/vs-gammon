# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
The owner, a strong online backgammon player (BackgammonGalaxy, about 2250 Elo, username chessgamm0n), plus a few others he shares it with: friends, students or teammates. They know the game well but not every analysis term, so terms such as equity, EMG, PR or "double/take" get short, in-place explanations instead of being assumed. Used mainly at a desk on a Mac (laptop or desktop, keyboard and mouse), in sessions after playing a match.

## Product Purpose
VS Gammon turns the user's own played matches into training. It imports Jellyfish `.mat` match files (dropped in, or picked up automatically from a watched folder), has GNU Backgammon analyse every checker play and cube decision, shows where the player lost equity, lets them practise those exact positions until they get them right, and exports selected positions as eXtreme Gammon `.xgp` files. Success is the player making fewer and smaller errors over time: a falling PR, fewer blunders, missed positions turning into mastered ones.

## Positioning
The practice material is the player's own mistakes from their own games, graded by a world-class engine, not generic puzzles. Every position carries where it came from (match, game, move, score, cube) and comes back until it is solved.

## Operating Context
After a session on BackgammonGalaxy the player downloads the match file. The app imports and analyses it within seconds. The player then reviews what went wrong (board, played move vs best move, candidate equities), practises the due positions, and occasionally exports positions to study further in eXtreme Gammon. Runs locally in Docker on a Mac at http://localhost:5563; one machine, no accounts.

## Capabilities and Constraints
- Pages: dashboard home (decided in this redesign: recent matches, PR trend, recurring mistakes, due practice together), matches/import, review, practice, history, settings.
- Import: drag-and-drop upload and watched folders (read-only access to the home folder, scanned every 30 s by default); duplicates are skipped by content hash.
- Analysis: GNU Backgammon 1.08 at 0–3 ply (2-ply default, equals XG 3-ply); thresholds doubtful / bad / very bad, presets gnubg 0.03/0.06/0.12 and XG-style 0.02/0.04/0.08, or custom; changing thresholds reclassifies instantly.
- Review: filter by match, player, checker/cube, severity, game; board with move arrows (game move, best move, any candidate); candidate equities and win/gammon chances; cube equities (no double, double/take, double/pass); XGID copy; select and export `.xgp` as a ZIP.
- Practice: click-to-move board (legal targets highlighted, undo/reset, keyboard), cube quizzes (No double/Double, Take/Pass), grading by equity loss (correct = below doubtful threshold), missed positions re-queued and kept "due" until solved, per-position history, stats (positions, new, missed, mastered, accuracy).
- History: timeline of imports, analyses (with per-player PR summary), failures, duplicates, exports, folder changes.
- Stack: Flask backend; frontend is vanilla HTML/CSS/JS with no build step, served from `app/static/`. No external runtime dependencies are required; web fonts may be self-hosted.
- Undecided: whether the app will ever run on tablets or phones (desktop is the target; layouts must still not break on smaller widths).

## Brand Commitments
- Visual direction (chosen Nov 2026): the category standard for backgammon analysis tools, executed at full craft, not a novel world. Quality bar: BackgammonGalaxy's blunder review (blue board, move list beside it), Linear (crisp light/dark product UI, keyboard-first), Chess.com / Lichess analysis and puzzles (board-first review, move arrows), Duolingo-style trainers (clear right/wrong feedback, progress you can feel).
- Light and dark modes are both first-class.

## Evidence on Hand
One real match file (`chessgamm0n_fishsoup_09112026_50469849.mat`, 3-point match, 2 games, 187 analysed decisions) and one XG position file (`xgp.xgp`). No practice history yet. No logo or brand assets exist.

## Product Principles
- The board is the main object; numbers explain the board, never replace it.
- Every position shows where it came from: match, game, move, score, cube.
- Show the cost of a mistake in equity and in plain words, side by side.
- Practice is the core loop: import → review → practise → master; each step is one click from the previous one.
- Calm and focused for long sessions: keyboard-first, no noise, nothing competing with the position.

## Accessibility & Inclusion
Readable for long evening sessions in both light and dark modes; meaning (error severity, correct/wrong, move colours) is never carried by colour alone; full keyboard use for practice and review.
