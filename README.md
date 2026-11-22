# Teeko AI

**CSE 3210 – Artificial Intelligence Lab** · Sumaiya Afrin Eva (2207039) · Md. Shomik Shahriar (2207041)

Teeko is John Scarne's 1952 game for two players on a 5×5 board. This project includes:

- a complete, playable version of the game, with two custom one-use abilities (**Swap** and **Fly**) and a movement limit with board scoring
- two independent AI agents:
  - **Minimax with alpha–beta pruning**
  - **Monte Carlo Tree Search (UCT)**
- a Pygame interface styled after our proposal
- AI-vs-AI controls, series auto-play, a benchmark, and a test suite

---

## 1. Setup and run

**Requirements:** Python **3.10 or newer** and `pygame-ce` (see [requirements.txt](requirements.txt)).

### Windows (easiest)

1. Double-click **`setup.bat`**. It finds a Python ≥ 3.10, creates `.venv` and installs the requirements.
   - It ignores older Pythons that may be first on PATH.
2. Double-click **`run.bat`** to play. If `.venv` is missing, it runs the setup first.

If you have no suitable Python yet, install one first:

```
winget install -e --id Python.Python.3.12 --scope user
```

### Manual (any OS)

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt      # macOS/Linux: .venv/bin/python
.venv\Scripts\python main.py                                 # the game
.venv\Scripts\python bench.py --games 10 --level medium      # benchmark (command line)
.venv\Scripts\python -m unittest discover -s tests -v        # tests
```

### Controls

| Action | How |
|---|---|
| Place a piece | Click an empty point. |
| Move a piece | Click one of your pieces, then a highlighted amber point (diagonals allowed). |
| Swap / Fly | When available, click the amber **Swap** or **Fly** button in *Special moves*, then follow the hint under the board. |
| Cancel a selection | Esc |
| AI vs AI | **Space** starts, pauses and resumes. **N** steps one move. **R** restarts. |
| Fullscreen | F11, or the □ button in the title bar. |

---

## 2. Rules implemented

**Standard Teeko**
- 5×5 board; Red (P1) and Blue (P2) have four pieces each. Red moves first.
- **Placement phase:** players alternate placing pieces until all eight are on the board.
- **Movement phase:** each turn, move one piece to an adjacent empty point, horizontally, vertically or diagonally.
- **Win:** four pieces in a row, column or diagonal, or on the four corners of a 2×2 square.
  - That makes 44 winning patterns: 10 horizontal + 10 vertical + 8 diagonal + 16 squares.
  - A win can also happen during placement.

**Custom rules (from our proposal)**
- **Shuttle trigger:** a player shuttles when the same piece moves back and forth between the same two cells over four of that player's own normal moves (A→B, B→A, A→B, B→A).
  - At that point the **opponent** permanently unlocks Swap and Fly.
  - The opponent's turns in between do not break the sequence.
  - Any other move by the shuttling player breaks it, and so do that player's own Swap or Fly.
  - Each player's sequence is tracked separately.
- **Swap:** exchange one of your pieces with one opponent piece.
- **Fly:** move one of your pieces to any empty point.
- Swap and Fly:
  - can only be used in the movement phase
  - can each be used **once per game** per player, even if the trigger happens again
  - use up your turn
- **Movement limit:** 24 movement turns per player (adjustable).
  - Steps, Swaps and Flies all count; placements do not.
  - The game ends once both players have used their turns, normally right after P2's 24th move.
- **Limit scoring:**
  - Score every winning pattern that contains no opponent piece: +1, +3 or +10 for 1, 2 or 3 own pieces.
  - Higher total wins; on a tie, more pieces in the central 3×3 wins; otherwise it's a draw.

**Clarifications we chose**
- **Win checks**, after every action:
  1. The mover's patterns are checked first.
  2. Then the opponent's patterns. Only a Swap can move opponent pieces, so a careless swap can hand the opponent a win.

  A win always beats limit scoring, including on the final permitted turn.
- **The PDF's "repetition penalty"** only affects the AIs, not the rules. Both AIs prefer not to recreate a position (same board, same player to move) that already occurred in the game. Such moves are marked ↺ in the move list.
- **No pass rule is needed.** Any four pieces always have at least five free neighbouring points, so a player can never be fully blocked. An exhaustive test checks this.
- **Turn limit:** our proposal slides said 25 movement turns; the final specification uses 24. The setup screen can change it.

---

## 3. Architecture

```
            ┌───────────────────────── teeko/ui  (Pygame) ─────────────────────────┐
            │ start screen · game screen · benchmark screen · board view · widgets │
            └──────────────┬───────────────────────────────────────┬───────────────┘
                           │ update()/events (main thread only)    │ background thread
            ┌──────────────▼──────────────┐         ┌──────────────▼──────────────┐
            │ teeko/game/match.py         │         │ teeko/game/tournament.py    │
            │ Match, Series (auto-play)   │         │ headless games, benchmark,  │
            │ Start/Pause/Resume/Step/    │         │ multiprocessing workers     │
            │ Restart, move validation    │         └──────────────┬──────────────┘
            └──────────────┬──────────────┘                        │
                           │ immutable state + frozenset(visited)  │
            ┌──────────────▼──────────────┐                        │
            │ teeko/game/runner.py        │ (search runs in a daemon thread)
            └──────────────┬──────────────┘                        │
            ┌──────────────▼───────────────────────────────────────▼──────────────┐
            │ teeko/ai      minimax.py · mcts.py · evaluation.py · presets.py     │
            └──────────────┬──────────────────────────────────────────────────────┘
            ┌──────────────▼──────────────────────────────────────────────────────┐
            │ teeko/engine  board.py · state.py · rules.py · notation.py          │
            │ the single source of truth: legal_moves(), apply_move(), scoring    │
            └─────────────────────────────────────────────────────────────────────┘
```

### The engine (`teeko/engine`)

The engine is pure Python and knows nothing about the UI or the AIs.

- **Board representation:** each side is a 25-bit integer (one bit per point).
- **State:** a `GameState` is immutable and holds:
  - both boards and the player to move
  - the movement counters
  - each player's last step and shuttle streak
  - Swap/Fly unlocked and used flags
  - the limit and the result
- **Two keys:**
  - `position_key()` is the board plus the player to move. It is used for repetition.
  - `state_key()` adds everything else that affects future play: counters, streaks, ability flags and the limit. The transposition table uses it, so the same board with different special-move availability counts as a different state.
- **Shared rules:** `legal_moves(s)` and `apply_move(s, move)` are used by the UI, the match controller and both AIs. The match controller re-validates every move an AI returns, so an AI can never make an illegal move.

### The game layer (`teeko/game`)

- `Match` drives a game frame by frame and keeps the move history and visited positions.
- When an AI is to move, `Match` hands the background search an **immutable snapshot** of the state and a `frozenset` of the visited positions, plus a game token. Results from an earlier game (before a Restart) are discarded.
- Only the main thread changes the match or draws.

---

## 4. Minimax with alpha–beta (`teeko/ai/minimax.py`)

**Search**
- **Negamax form:** every score is from the point of view of the player to move.
- **Terminal scores:** `+1,000,000 − ply` for a win and `−1,000,000 + ply` for a loss, so the AI prefers quick wins and slow losses. A draw is 0.
- **Alpha–beta pruning** cuts branches that cannot change the decision.
- **Iterative deepening** searches depth 1, 2, …, up to the level's depth. When the time budget runs out, it uses the **deepest fully completed** iteration. Depth 1 always completes, so a legal move is always returned.
- **Transposition table** keyed by `state_key()`. It stores exact values or bounds plus the best move, and mate scores are adjusted for distance.
- **1-ply extension:** if the player to move at a node can win immediately, the node gets the exact win score. Wins by step, placement, Swap or Fly all count.
- **Move ordering:**
  1. the best move from the transposition table
  2. moves that occupy a cell where the opponent would win
  3. killer moves
  4. history heuristic
  5. a cheap "pattern gain" score

  Single-use specials are tried late unless they win or block.

**Heuristic evaluation** (`evaluation.py`, at the depth limit), with these terms:
- progress in open lines and 2×2 squares (weights 2 / 9 / 45 for 1 / 2 / 3 own pieces), minus the same for the opponent
- the opponent's winning threats for next turn, including threats Swap or Fly make possible. Two separate threats are nearly lost; one threat must be blocked.
- control of the central 3×3 and mobility
- Swap/Fly: available > locked but unused > used
- shuttle streak: approaching the fourth shuttle move is penalised, because it unlocks the opponent's specials
- the real +1/+3/+10 limit-score difference, weighted more heavily as movement turns run out

**Repetition penalty, from the chooser's point of view**
- If action *a* leads to an already-visited position, its value is `−v(child) − REP_MM`, with `REP_MM = 8` evaluation points.
- To keep pruning exact, that child is searched with the window shifted by the penalty: `(−β − REP, −α − REP)`.
- Only real game history is penalised. That history is fixed during one decision, so cached table entries stay valid.

---

## 5. Monte Carlo Tree Search (`teeko/ai/mcts.py`)

This is a separate algorithm. It has no evaluation function: it learns from simulated games. Each iteration has four steps:

1. **Selection:** descend the tree, always choosing the child with the highest
   `UCT = Q/N − pen + C·√(ln N_parent / N)`
   - `Q/N` is the child's average reward for the player who chose it.
   - C = √2.
   - `pen = REP_MCTS = 0.05` (in reward units) if the child's position already occurred in the game.
2. **Expansion:** add one untried legal move as a new node.
3. **Simulation:** play the game to the end with the rollout policy, using the same rules engine. Specials, triggers, the movement limit and limit scoring all apply. The rollout policy:
   - plays an immediate win if one exists
   - otherwise tries actions in random order (normal moves first; specials first only 10% of the time) and plays the first **safe** one. An action is safe when the opponent then has no immediate winning reply, including one by Swap or Fly or by specials the action itself unlocked. Safety is checked with the engine.
   - plays a random legal action if nothing is safe
4. **Backpropagation:** add 1 for a win, 0.5 for a draw and 0 for a loss to every node on the path, from the point of view of the player who moved into that node.

**MCTS-Solver** (Winands et al., 2008)
- Plain UCT averages are slow to notice sharp tactics. During calibration it even missed a one-move placement threat.
- So the tree also tracks **proven** results:
  - a node is proven when its game is over, or when the player to move there can win at once
  - proofs propagate up the tree
- Selection never enters a proven-lost child while an alternative exists.

**Budgets and the final move**
- The search stops when the simulation budget or the time budget runs out.
- It plays the **most-visited** root move, preferring a proven win and avoiding proven losses.
- An immediate win at the root is played without simulating (reported as `shortcut`).
- The statistics separate *completed* simulations from the configured maximum.

---

## 6. Difficulty levels

These were calibrated on an i7-13620H with Python 3.12, where Minimax searches about 50–140k nodes/s and MCTS completes about 2,500 simulations/s over a whole game. Time budgets are caps, not guarantees.

| Level | Minimax | MCTS | Time budget |
|---|---|---|---|
| Easy | depth 1, random choice among near-best moves | 300 simulations | ≤ 1 s |
| Medium (default) | depth 4 | 3,000 simulations | ≤ 2 s |
| Hard | depth 6 | 8,000 simulations | ≤ 4 s |
| Expert | depth 8 | 20,000 simulations | ≤ 8 s |
| Custom | depth 1–10 | 100–30,000 simulations, exploration C | 0.5–10 s |

With Swap/Fly unlocked a position can have around 100 legal moves. Depth 7 can then take about 15 s, so the time caps and iterative deepening keep every level within budget.

---

## 7. Benchmark

There are two ways to run it:
- **In the app:** the *Benchmark* card on the start screen.
- **From the command line:**

  ```
  python bench.py --games 10 --level medium --jobs 8 [--mm-level hard] [--mcts-level hard]
                  [--time 1.0] [--openings 2] [--limit 24] [--seed 1] [--csv games.csv] [--json summary.json]
  ```

It plays all four pairings: Minimax v Minimax, Minimax v MCTS, MCTS v Minimax and MCTS v MCTS. It reports win rate, average game length and average decision time.

**Fairness**
- The Minimax-vs-MCTS comparison pools both cross pairings, so **each algorithm plays as P1 and as P2 equally often**.
- Game *i* of both cross pairings shares a seed: the same random opening, with sides swapped.
- Results appear **per algorithm** and **per seat**, so first-player advantage is visible on its own.
- The same seed reproduces the same games when budgets are depth- or simulation-limited. Wall-clock time caps can add small variations.

### Sample results

This run used Medium vs Medium: 10 games per pairing, 2 random opening plies, seed 1 and 8 worker processes, on an i7-13620H. Decision times are measured with 8 games running in parallel. Command: `python bench.py --games 10 --level medium --jobs 8`.

| Pairing (P1 v P2) | P1 win | P2 win | Draw | Avg actions | P1 time | P2 time | End reasons |
|---|---|---|---|---|---|---|---|
| Minimax v Minimax | 30% | 60% | 10% | 50.1 | 0.03 s | 0.02 s | limit score 5, line 3, square 1, draw 1 |
| Minimax v MCTS | 90% | 10% | 0% | 34.4 | 0.06 s | 1.63 s | line 6, limit score 3, limit centre 1 |
| MCTS v Minimax | 0% | 100% | 0% | 23.2 | 1.71 s | 0.05 s | line 10 |
| MCTS v MCTS | 50% | 50% | 0% | 42.7 | 1.57 s | 1.53 s | limit score 6, line 3, square 1 |

| Sides balanced | Wins | Losses | Win rate | As P1 | As P2 | Avg decision |
|---|---|---|---|---|---|---|
| Minimax (depth 4) | 19 | 1 | 95% | 9/10 | 10/10 | 0.05 s |
| MCTS (3,000 simulations) | 1 | 19 | 5% | 0/10 | 1/10 | 1.66 s |

**What it shows**
- Minimax is clearly stronger at the same level while using about **30× less time per move**.
- Teeko is small and highly tactical, and a decisive mistake is usually only a few plies deep. A shallow alpha–beta search with a tuned evaluation sees these mistakes exactly. MCTS has to discover them statistically from random-ish playouts.
- MCTS does improve with budget. During calibration, 3,000 simulations beat depth-1 Minimax 6–0 and was roughly even with depth 2.
- The per-seat columns of the mirror pairings show a seat effect in this sample (Minimax v Minimax: P2 won 60%). Pooling both cross pairings removes that effect from the algorithm comparison.

---

## 8. Tests

```
.venv\Scripts\python -m unittest discover -s tests -v
```

| File | Covers |
|---|---|
| `test_rules.py` | geometry and the 44 patterns; placement and movement; wins of every kind; no false wins; win precedence for every action type; exact `winning_moves`; random-game invariants; the exhaustive "never blocked" proof |
| `test_specials.py` | locked at start; unlock on exactly the 4th shuttle move; what breaks a sequence; separate streaks; Swap/Fly effects, single use, turn use and independence; no specials during placement |
| `test_scoring.py` | +1/+3/+10 scoring against an independent implementation; centre tie-break and draws; P1 = 24 / P2 = 23 continues; a win on the final turn beats scoring; configurable limit |
| `test_minimax.py` | legal moves; wins, blocks, forced 3-ply wins, Swap/Fly wins; alpha–beta equal to plain minimax **with** repetition penalties; penalty sign; time caps; cancellation |
| `test_mcts.py` | root visits = completed simulations; time budget; win shortcut; blocking; solver proofs; repetition avoidance; rollout safety; 1,000 rule-checked rollouts |
| `test_match.py` | all four pairings finish; Start/Pause/Resume/Step/Restart; stale results dropped; AI move validation; immutable snapshots; series side alternation; benchmark fairness, reproducibility and parallel = serial |
| `test_ui_smoke.py` | the real screens driven headlessly by clicks: Human vs AI, all four AI-vs-AI pairings, a series, Swap in Human vs Human, the benchmark screen |

---

## 9. Project structure

```
main.py  bench.py  setup.bat  run.bat  requirements.txt
assets/fonts/      Fredoka (SIL Open Font License, see OFL.txt)
teeko/engine/      board.py  state.py  rules.py  notation.py
teeko/ai/          base.py  evaluation.py  minimax.py  mcts.py  presets.py
teeko/game/        match.py  runner.py  tournament.py
teeko/ui/          app.py  theme.py  gfx.py  widgets.py  board_view.py  settings.py
                   setup_screen.py  game_screen.py  benchmark_screen.py
tests/             helpers.py + one test file per area
```

The Fredoka typeface (© The Fredoka Project Authors) is used under the SIL Open Font License 1.1. The static weights were generated from the variable font.
