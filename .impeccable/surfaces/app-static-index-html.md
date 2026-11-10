---
version: 1
slug: "app-static-index-html"
primary_target: "app/static/index.html"
related_targets: ["app/static/review.html","app/static/practice.html","app/static/history.html","app/static/settings.html"]
---

# Surface brief: VS Gammon app shell (all pages)

Scope: the whole web app (dashboard, matches, review, practice, history, settings). Mode: Operate.
Audience and job: a strong player (plus a few friends) at a Mac after a match: see how they played, review the errors, practise them until solved.
Constraints: vanilla HTML/CSS/JS, no build step; light and dark modes; keyboard-first practice and review.

## Direction contract

THESIS: The category standard for backgammon analysis, done at full craft: a dark navy (or clean light) product shell with a blue Galaxy-style board as the one object that matters. It refuses the old app's generic Material cards and the "grey screen with one blue button".

OWN-WORLD: Navy ink shell with a quiet sidebar; slate surfaces stepping up a few % each level; one blue accent; a blue two-tone board with white and indigo checkers; severity in amber/orange/red, correct in green; move arrows red (game), green (best), amber (yours). Inter at a 1.25 scale, tabular numbers everywhere.

STORY: Land on the dashboard, see PR trend, where equity is lost by phase, and how many positions are due; start practice in one click; review any match board-first; export to XG.

FIRST VIEWPORT: Sidebar left (logo, Dashboard, Practice with due count, Review, Matches, History, Settings; theme switch at the foot). Dashboard: greeting row with "Start practice · 9 due" primary button; four stat cards (last PR with sparkline, errors per match, practice accuracy, due/mastered); PR trend chart and equity-by-phase bars side by side; biggest recent mistakes with mini boards; recent matches.

FORM: canon (the standing exit), chosen by the user over the dealt direction. seed:6e58582a9b3a5fd3

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
