# Paper Pipeline — Dependency Chain

## Architecture
Each stage runs in its own git worktree (isolated filesystem).
Output is committed to its branch, merged to main before next stage starts.

## Dependency Graph

```
Stage 1 (parallel):
  [theory-core]     → paper/sections/theory_endogenous_premium.tex
  [theory-greeks]   → paper/sections/theory_greeks.tex + theory_etf_comparison.tex
  [theory-capstruct]→ paper/sections/theory_optimal_capital.tex + theory_market_impact.tex
      ↓ merge all to main
Stage 2 (parallel):
  [math-review-cc]  → MATH_REVIEW.md + fixes to theory .tex files (Claude)
  [math-review-gem] → GEMINI_REVIEW.md + independent verification (Gemini 3.1 Pro)
  [theory-code]     → src/ updates: fair premium, mispricing, reflexivity gain, WACBA
      ↓ merge all to main  
Stage 3 (single):
  [paper-write]     → Complete paper: main.tex + all sections, theory-first structure, compiled PDF
      ↓ merge to main
Stage 4 (parallel):
  [final-review]    → Final math + prose review
  [final-code-qa]   → Run pipeline, verify all numbers match paper
      ↓ merge to main
Done: Submit
```

## Worktree Layout
~/Code/mstr-paper-v2/           — main repo
~/Code/mstr-wt/theory-core/     — Stage 1
~/Code/mstr-wt/theory-greeks/   — Stage 1
~/Code/mstr-wt/theory-capstruct/— Stage 1
~/Code/mstr-wt/math-review-cc/  — Stage 2
~/Code/mstr-wt/math-review-gem/ — Stage 2
~/Code/mstr-wt/theory-code/     — Stage 2
~/Code/mstr-wt/paper-write/     — Stage 3
~/Code/mstr-wt/final-review/    — Stage 4
~/Code/mstr-wt/final-code-qa/   — Stage 4
