# VS Gammon

A local web app that imports backgammon match files (`.mat`, the Jellyfish format exported by BackgammonGalaxy and others) and analyses every checker play and cube decision with **GNU Backgammon 1.08**. The engine runs inside the Docker container. The app lists errors and blunders, filtered by thresholds you set, and exports the positions you pick as eXtreme Gammon **`.xgp`** files in one ZIP.

## Mac app (no Docker)

`VS Gammon.app` is self-contained: the engine, Python and the interface are all inside it (Apple Silicon, macOS 13 or later). Open the `.dmg` and drag the app to Applications. It isn't notarized by Apple, so the first launch needs one approval: try to open it, then go to System Settings › Privacy & Security and choose **Open Anyway**.

Your matches live in `~/Library/Application Support/VS Gammon`, so updating or replacing the app keeps them. If the Docker version is installed, the first launch offers to copy its matches and practice history; the originals stay as they are. Settings › Updates installs new versions. Closing the window quits the app; watched folders are checked again on the next launch.

To build it: `packaging/macos/build-deps.sh`, `packaging/macos/build-gnubg.sh`, then `packaging/macos/build-app.sh` writes `dist/VS Gammon.app`. `packaging/macos/release.sh` also makes the `.dmg` and the signed update zip.

GNU Backgammon is free software under the GPL version 3; its source is at <https://ftp.gnu.org/gnu/gnubg/>.

## Install with Docker (macOS)

Needs Docker Desktop (the installer offers to install it with Homebrew) and git (the Command Line Tools). Open Terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/ruolez/vs-gammon/refs/heads/main/install.sh | bash
```

This installs into `~/vs-gammon` (set `VSG_HOME` for another folder) and does the following:
- **Downloads the app** from GitHub.
- **Starts the server:** it builds the image (Debian + GNU Backgammon) and starts it on port **5563**, or the next free port.
- **Adds a "VS Gammon" shortcut to your Desktop.** Double-clicking it opens the app. If the server is not running, the shortcut starts Docker Desktop and the server first, and shows a macOS alert if something goes wrong.
- **Imports an earlier install:** if it finds an earlier VS Gammon / Gammon Analyzer container, it offers to copy its matches, practice history and settings.

Your matches, practice history and settings live in `~/vs-gammon/data`, and exported ZIPs in `~/vs-gammon/exports`.

Run `~/vs-gammon/install.sh` with no argument for a menu, or with a command:

| Command | What it does |
|---|---|
| `update` | Backs up `data/` and fetches the latest version from GitHub. Removes files the app no longer uses (your data, exports, backups and `.env` are kept), rebuilds, restarts, prunes old images and refreshes the shortcut. Shows what changed. |
| `start` / `stop` | Starts the server and opens the app (the shortcut does the same) / stops it |
| `status` | Version, container state, health, shortcut |
| `backup` | Writes `backups/data-<timestamp>.tgz` (keeps the last 10) |
| `restore FILE` | Replaces the data with a backup, for example one copied over from another Mac |
| `shortcut` | Recreates the Desktop shortcut |
| `uninstall` | Removes the container, images and shortcut. Asks before deleting your data and backs it up to the Desktop first |

Add `--yes` to skip questions. The shortcut writes a log to `~/Library/Logs/VS Gammon.log`.

**Moving to another Mac:** run `install.sh backup` here, install on the new Mac with the curl line, then run `install.sh restore <backup file>` there.

## Using it

The sidebar has Dashboard, Practice (with the number of positions due), Review, Matches, History and Settings. The theme switch at its foot cycles light, dark and "match my Mac"; the sidebar collapses to an icon rail with the panel button or the `\` key.

The app speaks English and Russian: the EN/RU button at the foot of the sidebar switches at once, and Settings › Appearance has the same choice. A− and A+ next to it change the text size from 90% to 150% (also the `+` and `-` keys). Language, text size and theme are remembered in the browser.

- **Dashboard** (home): PR per match, errors per match, practice accuracy and streak, where you lose equity by game phase (opening, middle game, race, bear-off, cube), your biggest recent mistakes with mini boards, and recent matches. Settings › You picks which player is you; otherwise the most frequent player is used.

0. **Watch a folder (optional):** in Settings › Watched folders, click **Add folder…** and pick the folder your match files download to (e.g. Downloads).
   - The app checks it every 30 s (configurable). Any new `.mat` file is imported and analysed with no further action.
   - It skips files that are still being written, never imports the same match twice, and only reads your files (the home folder is mounted read-only).
1. **Matches** (`/matches`): drop `.mat` files on the page. Each file is queued and analysed in the background; a 3-point match takes about 2 s at 2-ply on an M-series Mac. Each player gets:
   - counts of doubtful, bad and very bad decisions;
   - an approximate PR (mean error × 500).
2. **Review:** filter by match (or all matches), player, checker or cube decisions, severity or a custom minimum error, and game.
   - Clicking a row shows the board, the XGID (copy and paste it into XG), and either the candidate moves or the no double / double-take / double-pass equities.
   - Keyboard: ↑ ↓ (or j/k) to move between rows, space to select.
3. **Export:** tick positions and press **Export N as .xgp (ZIP)**.
   - The ZIP holds one `.xgp` per position, named `p1-vs-p2_date_g<game>_m<move>_<player>_<kind>_<class>.xgp`, plus `index.csv`. The CSV lists the played move, the best move, the error and the XGID for each file.
   - A copy of each ZIP is kept in `exports/`.
4. **Practice:** quiz yourself on positions from your games.
   - **Choose a set:** player, error level, checker or cube, which positions ("due" = missed ones first, then new), and match.
   - **Checker plays:** click a checker and it moves by a die. When it can reach two points they light up green, and you click one. Undo with ⌫, reset with Esc, submit with ↵. Any legal play is accepted and graded against the engine.
   - **Cube decisions:** No double / Double, or Take / Pass (keys N/D, T/P).
   - **Feedback:** after each answer you see right or wrong with the equity lost, plus your move, the best move and the game move, as arrows on the board and in the candidate list.
   - **Scoring:** an answer counts as correct when it loses less than your "doubtful" threshold.
   - **Re-quizzing:** missed positions (and "Show answer") come back later in the same session and stay "due" until you get them right. Every attempt is saved.
5. **History:** a timeline of imports (upload or folder), analyses (with a PR summary per player), failures, duplicates, exports and folder changes.
6. **Settings:**
   - Threshold presets: GNU Backgammon 0.03/0.06/0.12, XG style 0.02/0.04/0.08, or custom. Changing thresholds reclassifies everything at once, without re-analysing.
   - Analysis depth (0–3 ply) and CPU threads. "Re-analyse all matches" applies a new depth to existing matches.

### How errors are measured

- All errors are equity lost in normalized match equity (EMG). Cube equities, which gnubg reports as match-winning chances in match play, are converted with gnubg's own `mwc2eq` at that decision's cube, score and Crawford state.
- **Checker play:** best candidate equity − played move equity. Only candidates evaluated at the full analysis depth are listed. Forced moves (a single legal play) are hidden unless "include forced moves" is ticked.
- **Double / no double:** compares no-double equity with min(double/take, double/pass).
- **Take / pass:** compares double/take equity with double/pass (+1.0), from the doubler's side.
- At the gnubg thresholds, this grading matches gnubg's own grade on every decision of the sample match (an integration test checks this).
- **PR is approximate.** It counts unforced checker plays, plus cube decisions that were acted on, wrong, or close (within 0.16 of the double/no-double boundary). XG's rules for which cube decisions count differ slightly.

### `.xgp` export

Files are written in XG's binary format: the `RGMH` header with a board thumbnail, then a zlib archive holding `temp.xg` and `temp.xgi`. They are built from a template position saved by XG (`app/xgp/template.xgp`).
- **Checker plays** are written as HeaderMatch + HeaderGame + Cube + Move, with the dice set.
- **Cube decisions** stop after the Cube record. A take decision is written with the double already offered.
- **No analysis is stored.** XG analyses the position itself when you open it.

**Not yet confirmed in XG itself:** that XG opens the generated files and shows the right position, side on roll, dice, cube and score. The test set in `exports/xg-test/` covers each case:
- a checker play for either player;
- a double, a take and a missed double;
- a Crawford-game position.

## Development

Work in a clone of the repo; `docker compose up -d --build` runs it from there (same container name and port as an install, so stop one before starting the other).

```bash
docker compose up -d --build                                    # http://localhost:5563
docker compose exec -T app python3 -m unittest discover -s tests -t .   # full suite, incl. real gnubg run
python3 -m unittest discover -s tests -t .                      # host: pure-logic tests (gnubg/Flask/Pillow tests need the container)
node --test tests/js/                                           # practice move logic (moves.js), incl. every legal move of a real match
```

```
app/
  main.py               Flask app + API (/api/matches, /api/decisions, /api/export, /api/settings, /health)
  db.py                 SQLite (WAL) helpers, migrations in app/migrations/
  jobs.py               background analysis worker (one gnubg process per match)
  analysis.py           error formulas, classification, per-player summary
  matfile.py            .mat header tags (Site, Match ID, Elo, date)
  importer.py           shared import path (upload + folder), dedupe by SHA-256, history events
  watcher.py            folder watcher: host path ⇄ /host mount, scan, settle time, folder browser
  position.py           board frames (gnubg ⇄ XG) and XGID
  engine/analyse_gnubg.py   runs inside `gnubg -t -p`: import mat, analyse match, dump JSON
  engine/walk.py        gnubg match dict → decision rows (cube/score tracking, .mat line numbers)
  engine/runner.py      subprocess wrapper with timeout
  xgp/archive.py        RGMH header + XG zlib archive (byte-exact round trip of XG's own file)
  xgp/records.py        2560-byte record field map
  xgp/writer.py         position → .xgp
  xgp/thumbnail.py      Pillow board thumbnail
  static/               vanilla HTML/CSS/JS (Matches, Review, Practice, History, Settings)
    js/moves.js         single-die steps + reachable legal plays (shared with Node tests)
    js/board.js         SVG board: perspective, arrows, clickable mode
tests/                  unittest suites + fixtures (sample .mat and XG .xgp)
```

GNU Backgammon is GPL-3. It runs as a separate program inside the container, which is fine for personal use. If you distribute the image, offer the gnubg source along with it.
