# Literature Extraction Subskill

Use this TraceGate subworkflow when a research project needs to audit whether
values in a parameter registry are actually supported by local source evidence.
It is designed for source-derived parameter work, especially when a registry
was built from PDFs, extracted text, tables, figures, supplementary files,
webpages, digitization outputs, or manual literature notes.

The core failure this subskill prevents is:

```text
The registry is internally consistent, but the value in the registry is not
what the cited source actually says.

The cited source is internally matched, but it is only a relayed source
and has not been checked against the original measurement paper or dataset.
```

The goal is not to make a parameter set look complete. The goal is to separate
direct source values, converted values, digitized approximations, derived
values, inferred values, conflicts, and missing values before any baseline
claim is allowed.

## Inputs and Outputs

Inputs:

```text
MECHANICAL_PARAMETER_REGISTRY.json or PARAMETER_REGISTRY.json
source_evidence/ containing downloaded PDFs, extracted text, webpages,
supplementary files, figure digitization files, tables, and notes
```

Outputs:

```text
audit_report.json
audit_report.md
proposed_fixes.json
```

`audit_report.json` is the machine-readable result. `audit_report.md` is the
human-readable explanation. `proposed_fixes.json` contains suggested registry
changes but must not be applied automatically.

## Hard Constraints

```text
Do not connect to the web.
Do not edit source files.
Do not edit registry files.
Do not run COMSOL or other solvers.
Do not use chat memory or model common sense as evidence.
All judgments must point to local source_evidence files.
If the source is unreadable, missing pages, OCR-damaged, or lacks a locator,
mark the parameter BLOCK or SOURCE_UNVERIFIED.
Do not rewrite source_status to a stronger class unless local source evidence
directly supports it.
```

If the user explicitly asks for fixes, output proposed patches separately. Use
`proposed_fixes` or `safe_patch_suggestions`; do not claim that fixes were
applied, because the default workflow is read-only.

## Required Audit Rounds

Run all eight rounds in order:

```text
R-1 Evidence file inventory
R0  Original value check
R0.5 Primary-source chain check
R1  Provenance completeness
R2  Evidence grade check
R3  Duplicate, lineage, and conflict check
R4  Physical consistency check
R5  Baseline admission check
```

Later consistency checks cannot rescue a failed R-1, R0, or R0.5 check.

## R-1 Evidence File Inventory

Before checking any parameter, inventory the evidence directory.

For every file under `source_evidence/`, record:

```text
path
sha256 hash
file type: PDF | txt | webpage | supplement | table | figure | digitization | note | unknown
readability: readable | unreadable | OCR_damaged | binary_only | missing
source_id or paper_id if inferable
page coverage if known
last modified time
```

Rules:

```text
If the registry cites a source_id with no corresponding local evidence file,
BLOCK that parameter.

If the only source file is unreadable, OCR-damaged around the value, or missing
the cited page/table/figure, mark SOURCE_UNVERIFIED or BLOCK.

If a PDF exists but no extracted text/table/figure artifact exists, the auditor
may still inspect the PDF if tooling is available, but must record that the
source was read from PDF rather than extracted text.

If a webpage is used, record whether it is a saved local page, text export,
markdown copy, or screenshot. Do not fetch it again from the internet.
```

R-1 output must include:

```json
{
  "evidence_inventory": [
    {
      "path": "source_evidence/paper.txt",
      "sha256": "sha256:...",
      "type": "txt",
      "readability": "readable",
      "source_id_candidates": ["SRC-001"],
      "notes": []
    }
  ],
  "registry_sources_without_files": [],
  "unreadable_or_damaged_sources": []
}
```

## R0 Original Value Check

Check whether each registry value is actually present in the cited source.

For every parameter, output:

```text
registry_parameter
registry_value
registry_unit
source_file
source_locator: page/table/row/column/figure/panel/curve/equation/line/supplement
paper_value
paper_unit
quoted_excerpt
match_type: EXACT | CONVERTED | DIGITIZED | DERIVED | INFERRED | NOT_FOUND | MISMATCH
conversion_formula if any
uncertainty if digitized or estimated
search_evidence if not found
status: PASS | WARN | BLOCK
```

Keep `quoted_excerpt` short. Prefer no more than one sentence or 25 words from
the source.

Evidence rules:

```text
Table:
  Verify the exact cell, row label, column label, units, and table caption.

Figure:
  Mark DIGITIZED or DIGITIZED_APPROXIMATE.
  Never mark SOURCE_DIRECT.
  Require digitization artifact, axis calibration, and uncertainty.

Body text:
  Provide page or extracted-text line number and short excerpt.

Equation:
  Provide equation number, formula, source inputs, and derivation steps.

Supplementary:
  Mark SUPPLEMENTARY or identify the supplement in source_anchor.

Converted value:
  Verify original value, conversion formula, conversion factor, target unit,
  assumptions, and intermediate numeric steps.

Derived value:
  Mark DERIVED.
  Record formula and every source input anchor.

Inferred value:
  Mark INFERRED.
  Require rationale and block baseline unless an accepted decision allows it.

Value not found:
  BLOCK and include search evidence.

Value mismatch:
  BLOCK and report the source value.
```

Example conversion:

```text
paper: 13.7% area expansion
registry: 6.6% diameter expansion
check: sqrt(1 + 0.137) - 1 = 0.0663
match_type: CONVERTED
```

Search evidence is mandatory for `NOT_FOUND`. Record:

```text
keywords searched
files searched
pages, tables, figures, or line ranges inspected
nearby candidate values found
why candidates were rejected
```

Automatic source-status rules:

```text
source says "not measured directly"      -> source_status must include INFERRED
source says "calculated from"            -> source_status must include DERIVED
source value only in supplementary files -> source_status must include SUPPLEMENTARY or source_anchor must identify supplement
source value only in figure              -> source_status must include FIGURE_DIGITIZED or DIGITIZED_APPROXIMATE
source does not contain the value        -> SOURCE_MISSING or remove parameter from baseline set
```

## R0.5 Primary-Source Chain Check

R0 only proves that the registry matches the cited local source. It does not
prove that the cited source is the original measurement source.

For every baseline candidate, classify the cited source:

```text
primary source:
  original measurement paper, original dataset, original datasheet, direct
  laboratory measurement, instrument export, or standard

relayed source:
  review, compiled table, secondary figure, secondary fit, literature range,
  digitized plot, re-fitted curve, transcribed value, or proxy
```

If the cited source is relayed, output:

```text
registry_parameter
cited_source_id
cited_source_class
primary_source_id
provenance_chain
chain_depth
per_hop_verification_status
primary_source_file
primary_source_locator
status: PASS | WARN | BLOCK
```

Required chain fields:

```text
primary_source_id
provenance_chain[] with source_id, role, verification_status, and locator when available
verification_status in:
  VERIFIED
  PRIMARY_SOURCE_VERIFIED
  VERIFIED_AGAINST_PRIMARY
  VERIFIED_AGAINST_PARENT
  CROSS_CHECKED_TO_PRIMARY
source_decision_id or provenance_decision_id for baseline use of a relayed source
```

Fail-closed rules:

```text
Baseline parameter + relayed source + no primary_source_id -> BLOCK
Baseline parameter + relayed source + no provenance_chain -> BLOCK
Baseline parameter + provenance_chain without primary hop -> BLOCK
Baseline parameter + unverified transfer hop -> BLOCK
Baseline parameter + declared primary source that is itself relayed -> BLOCK
Baseline parameter + relayed source + no accepted decision -> BLOCK
```

This check prevents a common evidence-laundering error: a digitized fit can
match the paper figure perfectly while the figure itself is a smoothed,
re-fitted, or misquoted representation of an older source. In that case the
value is not primary-source closed and must remain diagnostic or
SOURCE_INCOMPLETE until the original source is read.

## R1 Provenance Completeness

Check whether the source identity and locator are sufficient.

For each parameter, verify:

```text
paper_id exists
source_id exists
DOI or stable source identifier exists when available
local source file exists under source_evidence/
source file hash or manifest artifact id exists when available
locator is specific: page/table/figure/equation/line/caption/supplement
material name is specific enough for the registry claim
measurement condition is recorded when condition-dependent
```

BLOCK if a baseline parameter lacks a usable source anchor.

WARN if the source is real but the anchor is too coarse, such as only a paper
title without page, table, figure, equation, or line locator.

## R2 Evidence Grade Check

Check whether `evidence_grade` is inflated.

Expected strength ordering:

```text
direct same-system measured
  > same-system derived
  > same-system digitized
  > close-system measured
  > cross-system transferred
  > inferred
  > proxy
```

Flag or downgrade when:

```text
A/B grade assigned to a different material system
A/B grade assigned to digitized figure-only data
A/B grade assigned to derived, inferred, fitted, or assumed values
C grade assigned without cross-system transfer rationale
D grade used with baseline_allowed=true and no decision/sweep rationale
figure digitized value graded above D without accepted decision and QA artifact
secondary-source repeat counted as independent evidence
```

Do not let a clean-looking registry table hide weak evidence.

## R3 Duplicate, Lineage, and Conflict Check

Detect repeated values, secondary-source reuse, and contradictory source values.

Duplicate and lineage checks:

```text
different paper_id but same numeric value, unit, and wording
review paper repeating a primary paper value
manufacturer datasheet reused through secondary literature
same value copied into multiple parameters under different names
same parameter listed once as measured and once as inferred
```

Conflict checks:

```text
multiple sources report different values for the same parameter
same source reports different values under different conditions
registry uses one value from a range without selection policy
main text and supplementary disagree
figure-derived value disagrees with table/text value
```

For every conflict, output:

```json
{
  "conflict_set": ["SRC-001", "SRC-002"],
  "parameter": "E_L",
  "values": [
    {"source_id": "SRC-001", "value": 120.0, "unit": "GPa", "condition": "dry"},
    {"source_id": "SRC-002", "value": 80.0, "unit": "GPa", "condition": "wet"}
  ],
  "likely_reason": "different material condition",
  "recommended_status": "SOURCE_CONFLICT",
  "baseline_allowed": false,
  "required_decision": "parameter_acceptance or source_conflict_resolution"
}
```

Policy:

```text
Conflicting values cannot enter baseline unless an accepted decision selects
one value, explains why, and records the excluded alternatives.

Duplicate secondary-source values do not count as independent support.
```

## R4 Physical Consistency Check

Check minimum physical coherence after source extraction.

This round cannot turn missing evidence into valid evidence. It only checks
whether already extracted values can coexist physically.

Examples:

```text
elastic constants:
  E, G, nu consistency where isotropic assumptions are used

Poisson ratio:
  plausible range and no impossible isotropic combination

swelling/expansion:
  sign convention, area-to-diameter conversion, linear-to-volumetric conversion

anisotropy:
  longitudinal vs transverse vs radial vs axial values not swapped

unit dimensions:
  Pa vs MPa vs GPa
  cm2/s vs m2/s
  percent vs fraction
  wt% vs vol% vs mol%
  mol/m3 vs mol/L
  area strain vs diameter strain vs volumetric strain

axis multipliers:
  log axis
  x10^-12 style axis multiplier
  normalized axes
  per mass vs per area vs per volume vs per active material vs per composite

condition dependence:
  temperature
  SOC, concentration, lithiation level, strain state
  strain rate
  electrolyte formulation
  dry/wet/electrolyte-swollen state
  loading mode
  sample direction
  particle/fiber/composite scale
  measured vs fitted vs assumed
```

## R5 Baseline Admission Check

Decide whether the parameter may enter the declared baseline.

Default policy:

```text
A/B evidence:
  allowed if source status is complete, source locator is precise, material and
  condition match, and implementation binding exists.

C evidence:
  allowed only with rationale and sensitivity/sweep or accepted decision.

D evidence:
  not allowed in baseline by default. May be used for diagnostic or bounded
  sweep only.

SOURCE_INCOMPLETE:
  requires source_decision_id and allowed_claim_level.

FIGURE_DIGITIZED:
  requires digitization artifact, uncertainty, axis calibration, and independent QA.

DERIVED:
  requires formula, inputs, conversion steps, and assumptions.

INFERRED:
  requires rationale and accepted decision before baseline.

SOURCE_CONFLICT:
  baseline_allowed=false unless a conflict-resolution decision is accepted.

SOURCE_MISSING, SOURCE_UNVERIFIED, or SOURCE_REJECTED:
  blocked.
```

## Additional Omission Checks

Run these checks when the source type makes them relevant.

### Source Integrity

```text
Check source version: main article, supplementary information, correction,
erratum, preprint, accepted manuscript, publisher version, or local copy.
Record if a value comes from supplement rather than main text.
Record if extracted text has OCR problems around the value.
Record whether the source is primary research, review, datasheet, or model paper.
```

### Locator Precision

```text
Every accepted value needs the smallest available locator:
table row/column, figure panel and curve label, equation number, page, line,
caption, supplementary file name, or digitization artifact path.
```

### Unit and Axis Multipliers

```text
Check axis multipliers such as x10^-12, %, kPa, MPa, GPa, cm2/s, mAh/g.
Check normalized axes and convert to absolute values only with recorded scale.
Check whether a value is per mass, per area, per volume, per composite, per
fiber, per active material, or per total electrode.
```

### Significant Figures and Ranges

```text
Record original significant figures.
Do not report digitized values with artificial precision.
Preserve ranges, confidence intervals, standard deviations, and error bars.
If registry stores a single value from a range, record selection policy.
```

### Direction, Sign, and Coordinate Convention

```text
Check longitudinal/transverse/radial/axial direction.
Check compression/tension sign convention.
Check expansion versus contraction convention.
Check whether negative values are physical or convention-driven.
```

### Material and Condition Match

```text
Check material composition, grade, fiber type, electrolyte formulation, porosity,
volume fraction, particle size, temperature, SOC/lithiation level, humidity,
strain rate, cycling state, test method, and sample preparation.
```

### Derived-Value Trace

For every derived value, record:

```text
formula
input source anchors
unit conversions
assumptions
intermediate numeric steps
uncertainty propagation when possible
```

### Negative Evidence

If a source explicitly says a value was not measured, was assumed, was fitted,
or was taken from another paper, record that statement. Do not treat the value
as direct measurement.

## Report Format

The report must be JSON and must include all rounds.

```json
{
  "audit_id": "LITERATURE_EXTRACTION_AUDIT_001",
  "status": "PASS | WARN | BLOCK",
  "input_registry": "PARAMETER_REGISTRY.json",
  "source_evidence_root": "source_evidence/",
  "outputs": {
    "json_report": "audit_report.json",
    "markdown_report": "audit_report.md",
    "proposed_fixes": "proposed_fixes.json"
  },
  "rounds": {
    "R-1_evidence_file_inventory": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "proposed_fixes": []
    },
    "R0_original_value_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "proposed_fixes": []
    },
    "R1_provenance_completeness": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "proposed_fixes": []
    },
    "R2_evidence_grade_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "proposed_fixes": []
    },
    "R3_duplicate_lineage_conflict_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "proposed_fixes": []
    },
    "R4_physical_consistency_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "proposed_fixes": []
    },
    "R5_baseline_admission_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "proposed_fixes": []
    }
  },
  "blocking_findings": [],
  "warn_findings": [],
  "conflict_sets": [],
  "recommended_registry_changes": [],
  "do_not_apply": true
}
```

Issue objects should include:

```json
{
  "parameter": "E_L",
  "round": "R0",
  "severity": "BLOCK",
  "finding": "registry value not found in cited source",
  "registry_value": {"value": 1.0, "unit": "GPa"},
  "source_value": null,
  "source_file": "source_evidence/paper.txt",
  "source_locator": "line 123",
  "quoted_excerpt": "short source excerpt",
  "search_evidence": {
    "keywords_searched": ["E_L", "longitudinal modulus"],
    "files_searched": ["source_evidence/paper.txt"],
    "locations_checked": ["Table 1", "lines 100-180"],
    "candidate_values_rejected": []
  },
  "recommended_action": "mark SOURCE_MISSING or remove from baseline"
}
```

## Prompt Template

Use this when delegating the audit to an agent:

```text
Use TraceGate literature extraction.

Inputs:
- MECHANICAL_PARAMETER_REGISTRY.json or PARAMETER_REGISTRY.json
- source_evidence/ with downloaded PDF/txt/webpage/supplement/table/figure/digitization evidence

Outputs:
- audit_report.json
- audit_report.md
- proposed_fixes.json

Constraints:
- Do not connect to the web.
- Do not modify any source or registry file.
- Do not run COMSOL or other solvers.
- Do not use chat memory or model common sense as evidence.
- All judgments must point to local source_evidence files.
- If original evidence is unreadable, missing, OCR-damaged, or lacks locator, mark BLOCK or SOURCE_UNVERIFIED.

Audit rounds:
R-1 Evidence file inventory: list source_evidence files, hashes, types, readability, and missing registry sources.
R0 Original value check: verify registry values against original source numbers, with source locator and short excerpt.
R0.5 Primary-source chain check: require relayed sources to trace back to original measurement evidence.
R1 Provenance completeness: verify DOI/source identity, material specificity, condition, and locator precision.
R2 Evidence grade check: detect inflated grades; direct same-system measured > derived > digitized > inferred > proxy.
R3 Duplicate, lineage, and conflict check: detect repeated secondary values and conflicting source values.
R4 Physical consistency check: check units, dimensions, signs, directions, conditions, and physical coherence.
R5 Baseline admission check: decide whether each parameter can enter baseline.

Rules:
- Figures are DIGITIZED_APPROXIMATE, never SOURCE_DIRECT.
- Reviews, compiled tables, secondary figures, secondary fits, digitized plots, and literature ranges require primary_source_id and a verified provenance_chain before baseline use.
- Derived or inferred values must be labeled as such.
- Values not found in the source are BLOCK and must include search evidence.
- Conflicting values require conflict_set, likely_reason, recommended_status, and baseline_allowed=false unless an accepted decision exists.
- Every round must output status, issues_list, and proposed_fixes.
```
