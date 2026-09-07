# PDF → HWP semantic reconstruction baseline

The [source-fidelity v2 work instructions](PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md)
supersede conflicting layout, content-preservation and release rules here.
The v2 update is documentation/design only: verify implementation and wiring in
the actual production entrypoint before claiming automatic enforcement.

This contract is the small bridge between the reviewed PDF/OCR manifests and
the HWP writer.  It is intentionally source-independent: real PDF, OCR,
HWP/HWPX, screenshots, and rendered pages remain local working evidence and
are never fixtures or Git inputs.

## Approved flow

```text
reviewed scope → reviewed OCR candidate → semantic item model
              → editable problem/solution HWP/HWPX checkpoint
              → native endnote (staged_atomic) → COM/reopen/render QA
```

Physical OCR rows are temporary evidence only.  The writer receives one
semantic item at a time, with its stem, ask, materials, condition/보기 box,
choices, tables, formulas, and owned figures.  A page without an included
problem/solution region is excluded before OCR.  A mixed page is cropped to its
reviewed item regions.  A page is never treated as one item.

Problem and solution regions are joined by a stable `item_id`; section,
printed label, problem first sentence, and solution content are all required
mapping evidence.  Printed number alone, page order, modulo, and
`page_round_robin` are not mappings.

## One-request execution with internal checkpoints

The user may request “convert and add endnotes” in one request.  That is a
single delivery request, not permission to bypass verification.  The runner
must still execute the following atomic checkpoints in order:

1. freeze the copyright-source hashes and the reviewed scope/region manifest;
2. reconstruct complete semantic problem and solution items (including side
   boxes, continuation blocks, choices, tables, figures, and formulas);
3. save and reopen the editable problem/solution HWP and HWPX and pass the
   semantic, formula, layout, and image audits;
4. only then insert one native endnote per reviewed item and run the endnote
   reopen/copy-move/render audit.

If a checkpoint fails, the runner must keep the last passing checkpoint and
stop the dependent stage.  It must not silently insert a page capture, plain
text formula, or incomplete solution into an endnote to make the counts match.
The final delivery is `PASS` only when every checkpoint and the final endnote
gate pass; otherwise the report is a staged candidate with explicit failure
codes and is not labelled complete.

Every solution item also declares `solution_completeness` with the number of
source blocks and reconstructed blocks plus an empty `omitted_block_ids` list.
Explanation boxes (for example 출제코드, 해설특강, 핵심개념), answer lines,
tables, figures, and continuation blocks are content blocks. A missing side box
is not cosmetic: `SOLUTION_CONTENT_INCOMPLETE` blocks the pre-endnote
checkpoint until the block is transcribed and reviewed. Do not remove an item
from the user's scope to pass QA; a scope change requires the user's direction.

## Semantic and native object rules

- HWP paragraphs must have `origin: semantic`; direct physical OCR-row
  paragraphs fail with `PHYSICAL_OCR_ROW_SPLIT`.
- Sentence units are complete reviewed sentences.  Fragments fail with
  `SENTENCE_FRAGMENTATION`. Normal automatic line wrapping is not a split
  sentence. Reconstruction must not summarize, invent choices, remove source
  fill-in proofs or fill their answer blanks.
- When the source item has choices, they are the exact reviewed count of ordered
  native choice objects in the reviewed layout; an open-response item declares
  `expected_choice_count: 0` and does not invent choices.
  `<보기>`/condition boxes and tables are native HWP tables, never raster
  captures.
- Only a tight-cropped pure figure may remain an image.  Page, question,
  solution-body, screenshot, and text-bearing captures are forbidden.  Each
  figure has exactly one owning `item_id`.
- When the default editable reflow profile is selected, body text uses
  함초롬돋움 11 pt and 160% line spacing. Paragraph spacing is
  native margins (0 pt before, 2 pt after); blank-line spacing is forbidden.
  Alignment must come from the selected, identified profile rather than an
  unverified historical pilot. Source-region layout takes precedence over
  generic page/column settings when requested. An alternative alignment must
  not stretch short/final lines. Record source measurements separately from
  chosen editable fonts and inspect effective run/paragraph properties.
- Equations are editable `eqed` objects using `HYhwpEQ`, 11 pt, and HWPX
  `baseUnit=1100`, with a non-empty script.  The reviewed source count,
  MathIR roots, writer occurrences, HWPX, HWP and reopened COM controls must
  form one count/owner/order chain. Compare rendered PDF regions visually;
  PDF does not expose native eqed controls. Compiled scripts use Hancom
  equation grammar only: raw LaTeX commands, ambiguous literal `!=`, and
  unbalanced braces/parentheses fail before HWP generation. Distinguish
  Factorial+Equal from a genuine NotEqual in the source AST; never fix the
  ambiguity with a global replacement. Subscripts,
  superscripts, sigma/product/limit bounds, fractions, roots, piecewise
  conditions, matrices, and vector symbols must remain structured native
  equation content rather than plain text.

**Correction to the earlier diagram rule:** diagram descriptions are review
metadata, not substitute figures. A graph, net, card/bag illustration, region
partition, or geometric drawing must remain an actual faithful drawing or an
approved tight pure-figure crop. A prose description, list of geometric
relations, or table describing shapes does not preserve the original figure.
`native_semantic`, `figure_reference`, and similar records cannot reach the
writer until an implemented, source-checked drawing or approved crop exists.
An ordinary source table can remain a native table; that does not authorize
replacing an arbitrary diagram by a table. Missing assets are hard failures.
Every retained crop needs exact source region, owner, role and actual SHA-256.

Before `EquationCreate`, use an explicit source dialect. `latex` is compiled by
`app/hwp_equation_compiler.py`; `hancom` is conservatively validated and is not
misrepresented as a fully parsed source MathIR. Auto-detection and mixed-dialect
regex stripping are forbidden. Unknown commands are errors, never identifiers.
TeX atom scope is retained (`x^12` is not silently interpreted as `x^{12}`);
reviewers write explicit groups when the source exponent is multi-character.
Visible escaped set braces remain visible; they cannot become grouping braces.
The compiler produces source-spanned presentation structure, not proof that an
OCR transcript agrees with the PDF. Operator exceptions (a source-written
lower-only sum or a bare operator symbol) must target the particular source
operator offset and have separate reviewed source evidence.

Run `app/hwp_authoring_preflight.py` on the **actual ordered authoring blocks**,
including nested table/choice cells, not a parallel self-reported count list.
It rejects missing dialects, unsupported formula commands, formula markup in
text, untyped mathematical cells, embedded OCR hard line breaks, description
figures, changed/missing assets, and content fields ignored by a text wrapper.
Check completeness metadata against the actual block lists; equal declared
counts alone do not prove that all source sentences or formulas are present.
It also rejects `FORMULA_OPERATOR_TOKENIZATION`: a tokenizer/OCR pass that has
split a command such as `\sqrt`, `\pi`, `\lim`, `\sum`, or `\int` into spaced
letters (`s q r t`, `p i`, etc.) is semantic formula damage even when the
resulting atom sequence happens to compile.  Such a block must be corrected
from the reviewed 600/900-dpi source before any HWP is generated.

`app/hwp_native_equation_writer.py` inserts the compiled script exactly once,
without a second lossy converter. Reopen both HWPX and binary HWP and compare
every COM equation's script, order, and BaseUnit with the compiled ledger.
Count equality alone is insufficient. Native readback still does not prove
visible layout: render and inspect matrices/cases column spacing, invisible
delimiters, accents, bounds and nested structures before release.

The v2 field-consumption contract also requires a closed content schema and a
ledger from source JSON pointers through normalized blocks and actual writer
events to saved/readback objects. An existing preflight's rejection of some
ignored fields is not proof of complete field consumption. Do not silently
choose only `text`, `components` or `segments` while losing nested conditions,
questions, tables or choices. Unknown content fields fail; metadata has an
explicit namespace. Preserve source reading order and trace one-to-many inline
run mappings without introducing artificial paragraph breaks.

These requirements must be wired into the real runner, including external work
scripts. Library tests alone do not validate a builder that bypasses them.
Bind source/scope/manifest/profile/code/output hashes to the release evidence;
changed dependencies invalidate affected downstream checks. A visual golden
file consisting of page images cannot serve as an editable golden file.

Keep `build_status`, syntax/asset audit status, source-fidelity status and final
release status distinct. A generated document is `REVIEW_REQUIRED` while
source-region/formula evidence, full text/table/figure comparison, all-page
layout, or native endnote mapping/copy-move evidence remains missing. Never
convert a count/style PASS or a stored VERIFIED label into a final PASS.

Synthetic checks (no real exam content):

```powershell
python tools/hwp_authoring_preflight.py reviewed-native-blocks.json --asset-root LOCAL_WORKSPACE --json authoring-qa.json
python -m pytest -q tests/test_hwp_equation_compiler.py tests/test_hwp_authoring_preflight.py tests/test_hwp_native_equation_writer.py tests/test_hwp_source_order.py tests/test_hwpx_content_snapshot.py
```

Merge reviewed chunks against the explicit ordered source inventory with
`app.hwp_source_order.order_reviewed_items`. Lexical ID order, chunk filenames,
and queue indexes are not source order. Reject duplicate/unknown IDs; require
full coverage by default. An explicitly partial work checkpoint must retain
every missing ID and the `INCOMPLETE` status. A candidate source inventory is
not made verified by ordering it correctly.

Compare saved pre-endnote and endnote content with
`app.hwpx_content_snapshot.read_hwpx_snapshot`: retain semantic paragraphs,
native equation scripts, table cell order/spans and package picture hashes.
Only empty paragraphs, paragraph-edge whitespace, automatic numbering and
layout metadata are ignored. Check note bodies against the corresponding
solution checkpoint and the remaining problem body against the problem
checkpoint. Unsupported visible objects fail this comparison rather than being
silently ignored. This proves checkpoint preservation, not source-PDF fidelity;
it also does not replace the real HWP copy/move and visual layout checks.

Hancom syntax reference: [official equation command explanations](https://help.hancom.com/hoffice/multi/ko_kr/hwp/insert/equation/equation%28explanation%29.htm).

## Endnote release gate

The default is `endnote_mode: staged_atomic`.  Native endnotes are not written
while content is still being reconstructed.  The pre-endnote editable HWP/HWPX
checkpoint must be `PASS` (and hash-addressed) before the native endnote stage
is scheduled.  Native endnote QA remains a separate final gate, including
HWP/HWPX reopen, COM inspection, copy/move tracking, and PDF render review.

Run the copyright-safe preflight with a local manifest:

```powershell
python tools/pdf_hwp_semantic_preflight.py reviewed-semantic-manifest.json `
  --json semantic-qa.json
```

The preflight is fail-closed.  The stable failure codes include
`PHYSICAL_OCR_ROW_SPLIT`, `BODY_JUSTIFY_STRETCH`,
`SENTENCE_FRAGMENTATION`, `CHOICE_LAYOUT_MISMATCH`,
`CONDITION_BOX_NOT_NATIVE`, `ITEM_COLUMN_MISMATCH`,
`FIGURE_OWNERSHIP_MISMATCH`, `PARAGRAPH_SPACING_OUT_OF_PROFILE`,
`OCR_UNREVIEWED`, `FORMULA_NATIVE_MISSING`, and
`FORMULA_UNSUPPORTED_SYNTAX`, and `SOLUTION_CONTENT_INCOMPLETE`.

The checked-in policy is
`config/pdf_hwp_semantic_reconstruction_policy_v1.json`, and the generic
validator is `app/pdf_hwp_semantic_reconstruction.py`.
