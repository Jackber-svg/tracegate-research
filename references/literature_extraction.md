# Literature Extraction Subskill

Use this TraceGate subworkflow when a research project needs to audit whether
values in a parameter registry are actually supported by the cited source
documents. The goal is not to make a parameter set look complete. The goal is to
separate direct source values, converted values, digitized approximations,
derived values, inferred values, and missing values before any baseline claim is
allowed.

## Scope

Inputs:

```text
MECHANICAL_PARAMETER_REGISTRY.json or PARAMETER_REGISTRY.json
source_evidence/ containing downloaded PDFs, extracted text, webpages, tables,
figures, supplementary files, and digitization artifacts
```

Output:

```text
audit_report.json
```

The audit is read-only by default:

```text
Do not edit the registry.
Do not connect to the web.
Do not run solvers.
Do not promote baseline.
Do not rewrite source_status to a stronger class unless the source evidence
directly supports it.
```

If the user explicitly asks for fixes, write proposed patches separately from
the audit report and mark them as suggestions.

## Required Audit Rounds

Run rounds in order. Later consistency checks cannot rescue a failed source
value check.

### R0 Original Value Check

Check whether each registry value is actually present in the cited source.

For each parameter:

1. Locate the cited source artifact under `source_evidence/`.
2. Locate the exact evidence anchor:
   - table cell
   - figure and digitized curve/point
   - equation
   - caption
   - supplementary table
   - body-text line
   - extracted-text line number
3. Compare the registry value against the source value.

Rules:

```text
Exact table/text match:
  PASS if numeric value, unit, material, condition, and direction match.

Converted value:
  PASS only if original value, conversion formula, conversion factor, target
  unit, and assumptions are recorded.

Figure value:
  Mark DIGITIZED_APPROXIMATE or FIGURE_DIGITIZED.
  Never mark SOURCE_DIRECT.
  Require digitization artifact and uncertainty estimate.

Derived value:
  Mark DERIVED.
  Record formula and all input source anchors.

Inferred value:
  Mark INFERRED.
  Require rationale and block baseline unless accepted by decision.

Value not found:
  BLOCK.

Registry value differs from source:
  BLOCK and report the source value.
```

Example conversion:

```text
paper: 13.7% area expansion
registry: 6.6% diameter expansion
check: sqrt(1 + 0.137) - 1 = 0.0663
classification: converted_match, not direct_match
```

R0 output lists:

```json
{
  "exact_match_list": [],
  "converted_match_list": [],
  "digitized_approximate_list": [],
  "derived_from_formula_list": [],
  "inferred_not_measured_list": [],
  "supplementary_source_list": [],
  "value_not_found_in_paper_list": [],
  "value_mismatch_list": []
}
```

Automatic source-status rules:

```text
source says "not measured directly"      -> source_status must include INFERRED
source says "calculated from"            -> source_status must include DERIVED
source value only in supplementary files -> source_status must include SUPPLEMENTARY or source_anchor must identify supplement
source value only in figure              -> source_status must include FIGURE_DIGITIZED or DIGITIZED_APPROXIMATE
source does not contain the value        -> SOURCE_MISSING or remove parameter from baseline set
```

### R1 Provenance Check

Check whether the source identity and anchor are sufficient.

For each parameter, verify:

```text
paper_id exists
DOI or stable source identifier exists when available
source file exists under source_evidence/
source file hash or manifest artifact id exists when available
locator is specific enough: table/figure/equation/page/line/caption/supplement
material name is not generic when the registry needs a specific system
measurement condition is recorded when the value depends on condition
```

BLOCK if a baseline parameter lacks a usable source anchor.

WARN if the source is real but the anchor is too coarse, such as only a paper
title without table, figure, or line locator.

### R2 Evidence Grade Check

Check whether `evidence_grade` is inflated.

Downgrade or flag when:

```text
A/B grade assigned to a different material system
A/B grade assigned to digitized figure-only data
A/B grade assigned to derived or inferred values
C grade assigned without explaining cross-system transfer
D grade used but baseline_allowed is true without decision/sweep rationale
```

Do not let a clean-looking registry table hide weak evidence.

### R3 Duplicate and Lineage Check

Detect repeated values that appear to come from the same original source.

Check:

```text
different paper_id but same numeric value, unit, and wording
review paper repeating a primary paper value
manufacturer datasheet reused through secondary literature
same value copied into multiple parameters under different names
same parameter listed once as measured and once as inferred
```

If duplicates are found, mark the primary source and secondary source lineage.
Do not count duplicated values as independent evidence.

### R4 Physical Consistency Check

Check minimum physical coherence after source extraction.

Examples:

```text
elastic constants:
  E, G, nu consistency where isotropic assumptions are used

Poisson ratio:
  plausible range and no impossible isotropic combination

swelling/expansion:
  sign convention, area-to-diameter conversion, linear-to-volumetric conversion

anisotropy:
  longitudinal vs transverse values not swapped

units and dimensions:
  Pa vs GPa, cm2/s vs m2/s, percent vs fraction, mol/m3 vs mol/L

condition dependence:
  temperature, SOC, strain rate, electrolyte formulation, sample direction,
  loading mode, dry/wet condition, particle/fiber/composite scale
```

R4 cannot turn a missing source into a valid source. It only checks whether
already extracted values can coexist physically.

### R5 Baseline Admission Check

Decide whether the parameter may enter the declared baseline.

Default policy:

```text
A/B evidence:
  allowed if source status is complete and implementation binding exists.

C evidence:
  allowed only with rationale and sensitivity/sweep or accepted decision.

D evidence:
  not allowed in baseline by default. May be used for diagnostic or bounded
  sweep only.

SOURCE_INCOMPLETE:
  requires source_decision_id and allowed_claim_level.

FIGURE_DIGITIZED:
  requires digitization artifact, uncertainty, and independent QA.

INFERRED:
  requires formula, assumptions, and accepted decision before baseline.

SOURCE_MISSING or SOURCE_REJECTED:
  blocked.
```

## Additional Omission Checks

Run these checks when the source type makes them relevant.

### Source Integrity

```text
Check source version: main article, supplementary information, correction,
erratum, preprint, accepted manuscript, or publisher version.
Record if a value comes from supplement rather than main text.
Record if extracted text has OCR problems around the value.
Record whether the source is primary research, review, datasheet, or model paper.
```

### Locator Precision

```text
Every accepted value needs the smallest available locator:
table row/column, figure panel and curve label, equation number, page, line,
caption, or supplementary file name.
```

### Unit and Axis Multipliers

```text
Check axis multipliers such as x10^-12, %, kPa, GPa, cm2/s, mAh/g.
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
strain rate, cycling state, and test method.
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
  "rounds": {
    "R0_original_value_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "auto_fixes_applied": []
    },
    "R1_provenance_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "auto_fixes_applied": []
    },
    "R2_evidence_grade_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "auto_fixes_applied": []
    },
    "R3_duplicate_lineage_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "auto_fixes_applied": []
    },
    "R4_physical_consistency_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "auto_fixes_applied": []
    },
    "R5_baseline_admission_check": {
      "status": "PASS | WARN | BLOCK",
      "issues_list": [],
      "auto_fixes_applied": []
    }
  },
  "blocking_findings": [],
  "warn_findings": [],
  "recommended_registry_changes": [],
  "tracegate_outputs_to_create": [
    "SOURCE_MANIFEST.json",
    "PARAMETER_REGISTRY.json",
    "DECISIONS.jsonl entries for SOURCE_INCOMPLETE items",
    "GATE_REPORTS/literature_extraction_audit.json"
  ]
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
  "source_anchor": "source_evidence/paper.txt:123",
  "recommended_action": "mark SOURCE_MISSING or remove from baseline"
}
```

## Prompt Template

Use this when delegating the audit to an agent:

```text
Use TraceGate literature extraction.

Inputs:
- MECHANICAL_PARAMETER_REGISTRY.json or PARAMETER_REGISTRY.json
- source_evidence/ with downloaded PDF/txt/webpage/table/figure evidence

Output:
- audit_report.json with R0-R5 findings

Audit rounds:
R0 Original value check: verify registry values against original source numbers.
R1 Provenance check: verify DOI/source identity, material specificity, and locator precision.
R2 Evidence grade check: detect inflated evidence grades.
R3 Duplicate and lineage check: detect reused values and secondary-source duplication.
R4 Physical consistency check: check units, signs, directions, ROM/Poisson/swelling coherence.
R5 Baseline admission check: decide whether each parameter can enter baseline.

Rules:
- Do not connect to the web.
- Do not modify registry files.
- Do not run solvers.
- Do not promote baseline.
- Figures are DIGITIZED_APPROXIMATE, never SOURCE_DIRECT.
- Derived or inferred values must be labeled as such.
- Values not found in the paper are BLOCK.
- Every round must output status, issues_list, and auto_fixes_applied.
```

