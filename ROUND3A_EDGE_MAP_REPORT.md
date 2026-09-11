# Round 3A Corrected Edge-Map Evidence Review

**Status:** authoritative corrected Round 3A review; frozen for Round 3B

## Scope and method

This review uses only the corrected Round 3A artifacts:

- `results_next_strategy/round3a/edge_map.csv`
- `results_next_strategy/round3a/by_pair.csv`
- `results_next_strategy/round3a/by_year.csv`
- `results_next_strategy/round3a/event_counts.csv`

No 2018-or-later data, strategy source, external data, or prior research result was read or used. The development years represented by `by_year.csv` are 2013--2017.

The unit of review is a mechanism, not a horizon row. Directional sides, magnitude bands, and adjacent horizons are assessed together. A nomination required: aggregate N at least 300; same-sign effect in at least 4 of 5 years; same-sign effect in at least 8 of 15 pairs where a 15-pair signal applies; mean absolute effect at least 0.05 ATR at a useful horizon; absolute t-statistic at least 2; and a coherent adjacent-horizon profile. Cross-sectional candidates additionally required replication in at least 2 of 3 fixed peer groups.

`edge_map.csv` contains 73 event-condition labels and 379 aggregate rows. Those labels were consolidated into 29 directional/session/regime/peer mechanism families before nomination; 5 families passed. The 379 rows were not treated as 379 discoveries.

## Nominated Round 3B mechanisms

| Rank | Mechanism | Evidence at useful horizon | Breadth and stability | Decision |
| --- | --- | --- | --- | --- |
| 1 | Market-structure-shift reversal (`mss_up`, `mss_down`) | H4: -0.0501 / +0.0631 ATR, t=-14.45 / +17.49; H8: -0.0560 / +0.0672 | H4 has 15/15 pairs and 5/5 years for both sides. The profile retains sign through H16. | Nominate |
| 2 | Order-block-candidate reversal (`ob_candidate_up`, `ob_candidate_down`) | H4: -0.0473 / +0.0621; H8: -0.0572 / +0.0691, t=-10.93 / +12.45 | H8 has 14/15 and 15/15 pairs; 5/5 years on both sides. H16 retains sign, with 4/5 years on the up side. | Nominate |
| 3 | M15 shock reversal (approved directional/magnitude branches) | Down 0.5--1.0 ATR, H4 +0.0500 (t=15.22), H16 +0.0619; up 1.0--1.5 ATR, H4/H8/H16 -0.0533/-0.0539/-0.0637 | 13--15/15 pairs and 4--5/5 years at qualifying horizons. Shape is persistent rather than a one-horizon spike. | Nominate, with exact branches frozen in register |
| 4 | London-open sweep reversal (`london_open_sweep_high`, `london_open_sweep_low`) | H16: +0.0620 / -0.0540 ATR, t=+4.53 / -4.43; H8 is +0.0492 / -0.0494 | High side: 12/15 pairs and 5/5 years at H16. Low side: 10/15 pairs and 4/5 years. Both sides have coherent monotone-or-near-monotone horizon development. | Nominate |
| 5 | Fixed-peer divergence convergence | At H4/H8/H16, mean effect is +0.354 to +0.486 ATR; t=94.0 to 108.2 | All 3/3 fixed peer groups replicate; every group is same-sign in 5/5 years at all three horizons; N is about 30k per group/horizon. | Nominate |

### Detail supporting the nominations

**1. Market-structure-shift reversal.** The two directional labels agree with the same reversal interpretation: `mss_up` is negative forward return and `mss_down` positive. At H4, the aggregate effects are -0.0501 and +0.0631 ATR; at H8, -0.0560 and +0.0672 ATR; at H16, -0.0608 and +0.0787 ATR. The up label has 15/15, 15/15, and 15/15 same-sign pairs at H4/H8/H16, and 5/5, 5/5, and 4/5 same-sign years. The down label has 15/15, 15/15, and 14/15 pairs, and 5/5 years throughout.

**2. Order-block-candidate reversal.** `ob_candidate_up` is negative and `ob_candidate_down` positive. The H8 effects, -0.0572 and +0.0691 ATR, meet the effect threshold on both sides and have t-statistics -10.93 and +12.45. At H4 the up side is just below the magnitude cutoff (-0.0473), but it is same-sign in 14/15 pairs and 5/5 years; H8/H16 provide the required useful-horizon evidence. This is a neighboring-horizon profile, not an isolated selection.

**3. M15 shock reversal.** The evidence supports a reversal family, but not a symmetric "all shocks" claim. The frozen branches are only `m15_shock_down_0_5_1_0`, `m15_shock_down_1_0_1_5`, and `m15_shock_up_1_0_1_5`. The first has +0.0500 ATR at H4 and +0.0619 at H16, with 15/15 then 14/15 pairs and 5/5 years. The upward 1.0--1.5 branch has -0.0533/-0.0539/-0.0637 ATR at H4/H8/H16, with 13/15, 13/15, and 11/15 pairs and 5/5, 5/5, and 4/5 years. Larger-shock branches are not silently included.

**4. London-open sweep reversal.** A sweep high is followed by positive returns and a sweep low by negative returns. The high side progresses +0.0380, +0.0492, and +0.0620 ATR across H4/H8/H16; the low side progresses -0.0373, -0.0494, and -0.0540. The H8 values narrowly miss 0.05 ATR but support the shape; H16 meets every aggregate criterion. This is therefore a late-horizon hypothesis, not proof of a short-horizon trade.

**5. Fixed-peer divergence convergence.** The three predeclared peer groups all meet the protocol independently: EURUSD/GBPUSD (+0.4859, +0.4635, +0.4709 ATR); AUDUSD/NZDUSD (+0.3663, +0.3546, +0.3539); and EURJPY/GBPJPY (+0.3708, +0.3560, +0.3598), at H4/H8/H16 respectively. Each has 5/5 same-sign years. This is the only cross-sectional family with demonstrated 3/3 peer replication.

## Important non-nominations and negative findings

| Family / finding | Why it was not nominated |
| --- | --- |
| OTE (`ote_up`, `ote_down`) | N is only 55--84, below the predeclared 300 minimum, regardless of visually large rows. |
| FVG, H1-aligned FVG, breaker, prior-sweep, sweep-then-MSS and ATR state labels | Several are statistically non-zero, but do not clear 0.05 ATR with the required breadth and stable neighboring horizon profile. `breaker_down` reaches +0.0508 only at H16; its preceding H4/H8 effects are +0.0488/+0.0422, so it is a near-miss rather than a standalone discovery. |
| Asia, London-body, and New York open range/extreme patterns | Some long-horizon rows approach the threshold, but the directional/session families do not provide a consistently qualifying two-sided profile. They are not promoted from one favorable row. |
| Larger M15 shocks | `m15_shock_up_gt_2_0` has a qualifying H4 row (+0.0565 ATR) but its sign is contrary to the nominated up-shock reversal branch and it lacks stable adjacent evidence. Other large branches miss year breadth or useful-horizon magnitude. |
| Basket persistence, strongest/weakest, residual, and strong-minus-weak rows | The corrected output does not show a 3-fixed-peer-group replication for a directly specified tradable pair construction. The very large `strong_minus_weak_change` statistics are retained as descriptive cross-sectional evidence, not converted into an unhedged trade hypothesis. |
| Directional asymmetry | The data do not support asserting that every up/down threshold, session sweep, or shock magnitude is equivalent. Round 3B contains only the explicitly listed branches. |

## Interpretation limits

The effects are pre-cost forward-return summaries in ATR units; they are not trade P&L, do not establish fillability, and do not establish independence between overlapping events. The high raw label counts also indicate persistence/overlap, so they cannot be reported as executable trade counts. The Round 3B register therefore uses a one-active-position, re-arm rule and conservative fixed costs. It remains a hypothesis register pending the separate, frozen Round 3C validation.

## Data-access attestation

This review did not read, run, inspect, or derive any result from 2018+ data. Round 3C was not implemented or run.
