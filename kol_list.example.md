# KOL list (template)

Copy this to `kol_list.md` and edit. `monitor.py` reads `kol_list.md` first, falls back to this `kol_list.example.md` if missing.

> Seed list reflects a crypto / DeFi / AI niche — swap rows for accounts in your own domain.

The `own` row is special — it's the only row read via the official X API (everything else routes through xapi.to). Replace `YOUR_HANDLE` with your X handle before the first real run.

| handle           | category        | weight | note                                     |
|------------------|-----------------|--------|------------------------------------------|
| YOUR_HANDLE      | own             | 1.0    | your account — official API owned-reads  |
| VitalikButerin   | l1-founder      | 0.9    | ETH                                      |
| aeyakovenko      | l1-founder      | 0.9    | SOL                                      |
| jefftokenomics   | defi-founder    | 1.0    | $HYPE — Hyperliquid (verify handle)      |
| nathanallman     | defi-founder    | 0.9    | $ONDO                                    |
| gdog97_          | defi-founder    | 0.9    | $ENA — Ethena                            |
| paulframbot      | defi-founder    | 0.9    | $MORPHO                                  |
| weremeow         | defi-founder    | 0.9    | $JUP — Jupiter                           |
| SergeyNazarov    | defi-founder    | 0.7    | $LINK                                    |
| StaniKulechov    | defi-founder    | 0.8    | $AAVE                                    |
| RuneKek          | defi-founder    | 0.7    | $SKY / Sky (ex-MakerDAO)                 |
| PrimordialAA     | defi-founder    | 0.7    | $ZRO — LayerZero                         |
| a1lon9           | platform-ops    | 0.9    | pump.fun                                 |
| StarXu_          | cex-ops         | 0.8    | OKX                                      |
| grapeot          | ai-builder      | 1.0    | workflow/AI benchmark                    |
| karpathy         | ai-builder      | 0.8    | AI / autoresearch reference              |

Format: pipe-separated markdown table. Columns:

- **handle** — X handle without `@`. The literal string `YOUR_HANDLE` causes a clear error so you can't accidentally run without setting your own.
- **category** — free-form tag. `own` is the only reserved value (marks your account).
- **weight** — float 0.0–1.0. Currently unused but reserved for future ranking.
- **note** — anything you want to remember. Common pattern: token ticker + flag like "verify handle" for entries you guessed at.

Handles flagged "verify handle" are starting guesses based on token names; check before relying on them.
