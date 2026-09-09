# RFBC Documentation Standard

> **Status:** Active standard  
> **Applies to:** all RFBC Markdown, PDF, DOCX, reports, manuals, runbooks, validation records and operating procedures  
> **Effective:** 9 September 2026

---

## Purpose

RFBC documentation must be technically precise **and** easy to scan. Formal documents should look like finished engineering/research material, not raw notes or terminal output.

## Visual hierarchy

Every formal document should contain, where applicable:

| Element | Standard |
|---|---|
| Title block | Document name, RFBC version, date, scope, status |
| Status panel | Research-qualified / broker-qualified / live-approved / pending |
| Executive summary | Decision first, evidence second |
| Section hierarchy | Short sections with descriptive headings |
| Tables | Prefer tables for rules, metrics, gates, broker properties and checklists |
| Callouts | Use blockquotes for IMPORTANT, WARNING, DECISION and PENDING items |
| Diagrams | Mermaid flowcharts for architecture, lifecycle and operating flows where useful |
| Checklists | Use checkboxes for live-enable, broker-validation and operational gates |
| Evidence links | Link directly to source files / raw results where available |
| Change status | Explicitly distinguish frozen strategy rules from execution overlays and future research |

## Markdown rules

- Avoid large unbroken paragraphs.
- Prefer concise tables over repetitive prose.
- Use horizontal rules to separate major sections.
- Keep heading depth shallow and consistent.
- Use **bold** only for decisions, thresholds and status terms.
- Use code blocks for exact ticket formats, commands and machine-readable examples.
- Use Mermaid only when it materially improves understanding.
- Never present a pending item as completed.
- Never blur research qualification with broker/live qualification.

## PDF / DOCX rules

Formal PDF and DOCX versions should use:

- clean cover page;
- consistent RFBC visual identity;
- restrained navy/blue accent palette;
- page header + footer with version/date;
- shaded status/decision callouts;
- alternating-row tables where useful;
- readable margins and spacing;
- no clipped tables, broken glyphs, crowded paragraphs or raw CSV dumps when a summary table is sufficient;
- clear page breaks around major sections;
- visual QA before release.

## Required status language

Use these status labels consistently:

- **FROZEN** - strategy logic cannot be silently changed.
- **RESEARCH-QUALIFIED** - independent testing passed.
- **BROKER-QUALIFIED** - exact broker symbol/economics/risk constraints verified.
- **LIVE-READY** - monitoring, risk and execution workflow tested end to end.
- **PENDING** - required work not yet completed.
- **REJECTED** - failed the frozen promotion or operational gate.

## Evidence chain

Each strategy/version must keep its own evidence chain. New strategy families, new RFBC versions, execution overlays and broker adapters must not overwrite the historical record of RFBC v1.0.

## Current RFBC v1.0 state

> **RESEARCH-QUALIFIED SET:** USDJPY + AUDJPY only.  
> **LIVE STATUS:** not yet fully live-ready. AUDJPYc broker validation, fresh account-equity sizing and final alert/end-to-end operational testing remain.
