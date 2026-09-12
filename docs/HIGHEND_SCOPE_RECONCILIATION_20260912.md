# HIGH-END 상·하 scope reconciliation (2026-09-12)

이 감사·재개 기록은 [USER_INTENT_EXECUTION_DEFAULT.md](USER_INTENT_EXECUTION_DEFAULT.md)를
공통 실행 원칙으로 따른다. 즉 명확한 변환·검증 요청은 가능한 독립 작업을 계속
수행하되, 원본 증거가 닫히지 않은 범위는 `evidence-open`으로 남기고 FINAL/PASS로
승격하지 않는다.

이 기록은 source 후보 manifest, reviewed subset manifest, 그리고 v6 HWPX의 정적
패키지 카운트를 대조한 범위 감사다. HWP/HWPX/PDF는 읽기만 했고 수정하지 않았다.
Hancom COM 실행, 재저장, source-fidelity PASS 또는 출고 PASS 선언은 수행하지 않았다.
파일명이 `완료` 또는 `final`이어도 아래 범위를 넘는 의미로 해석하지 않는다.

## 판정 요약

| subject | source candidate | reviewed subset | uncovered candidate | coverage | v6 endnote HWPX |
|---|---:|---:|---:|---:|---:|
| 고등수학(상) | 550 | 76 | 474 | 13.8182% | 76 |
| 고등수학(하), `001_050` | 371 | 50 | 321 | 13.4771% | 50 |
| 고등수학(하), `001_080` reference | 371 | 80 | 291 | 21.5633% | 해당 없음 |

세 행 모두 `PARTIAL_SCOPE`다. 숫자 equality가 없는 상태에서 full-book으로 표시할 수
없으며, equality가 생겨도 source fidelity·HWPX 편집성·COM readback·미주 품질을
증명하지 않는다.

## 고등수학(상)

근거 파일:

- `../../highend_four_subjects/math_up/problem_page_manifest.json`
- `../../highend_four_subjects/math_up/reviewed_manifest_strict_scope_076_20260906.json`
- `../../highend_four_subjects/math_up/reviewed_manifest_source_order_076_20260906.json`
- `../../highend_four_subjects/math_up/reviewed_scope_preflight_076_20260906.json`
- `../../../outputs/HIGHEND_4과목_HWP_HWPX_미주문서끝_개선후보_20260912_v6_comverified/고등수학상/고등수학상_미주작업_완료.hwpx`

`problem_page_manifest.json`은 source PDF 116쪽에서 문제 page 90개, 후보 item 550개를
기록하며 `status=SCOPE_CANDIDATE_NOT_VERIFIED`다. 26개 물리 쪽(표지·앞부분·개념·
구분 페이지 등)은 제외되어 있다. strict reviewed manifest는
`scope_id=MUP-REVIEWED-076-20260906`, `scope.item_count=76`,
`scope.inventory_item_count=550`, `missing_full_book_count=474`이며,
`release_status=NOT_VERIFIED_FULL_BOOK`, `strict_pass=false`, `scope_only=true`,
`buildable=false`다. reviewed ID는 후보 ID와 76개가 모두 일치하고 외부 ID는 없지만,
후보의 474개가 reviewed 범위 밖이다. source-order reference도 expected 550 / actual
76 및 `source_fidelity_proven=false`를 기록한다.

상 reviewed ID의 실제 묶음은 다음과 같다. 이 목록은 책 전체 순번이 아니라 선택된
비연속 범위다.

```text
MUP-01-A: 01–08 (8)
MUP-01-B: 1, 1-1, 2, 2-1, 4, 4-1, 5, 5-1, 6, 6-1 (10)
MUP-01-C: 01–16 (16)
MUP-02-C: 05–18 (14)
MUP-03-A: 01–06 (6)
MUP-03-C: 19–20 (2)
MUP-04-A: 01–08 (8)
MUP-04-B: 1, 1-1, 2, 2-1, 3, 3-1, 4, 4-1, 5, 5-1, 6, 6-1 (12)
```

v6 `고등수학상_미주작업_완료.hwpx`(SHA-256
`a2f1509be08c4dac464becc8e1ec2027dd9f85f7d09976fe6063eca441dfee10`)는 ZIP/XML 정적
검사에서 `hp:endNote` 76개와 `numType=ENDNOTE` 76개를 포함한다. 이는 위 76-item
subset과 개수상 일치하지만, XML에 source item ID가 들어 있지 않으므로
identity/source fidelity 증거는 아니다.

## 고등수학(하)

근거 파일:

- `../../highend_four_subjects/math_down/problem_page_manifest.json`
- `../../highend_four_subjects/math_down/source_inventory.json`
- `../../highend_four_subjects/math_down/reviewed_manifest_001_050.json`
- `../../highend_four_subjects/math_down/reviewed_manifest_001_080.json`
- `../../../outputs/HIGHEND_4과목_HWP_HWPX_미주문서끝_개선후보_20260912_v6_comverified/고등수학하/고등수학하_미주작업_완료.hwpx`

하 후보 manifest는 문제 page 60개, `item_count=371`이다. 후보 물리 쪽 범위는
`11–19, 22–31, 36–45, 47–55, 57–65, 69–74, 76–82`이며 source inventory도
`candidate_problem_page_count=60`, `estimated_total_problem_items=371`을 기록한다.
Step B는 인쇄번호 66개가 base/`-1` 변형 132개로 확장되므로, 인쇄번호 개수만 세면
후보를 66개 과소계수한다. 전체 chapter 합은 I 57, II 61, III 61, IV 57, V 55,
VI 37, VII 43이다.

`reviewed_manifest_001_050.json`은 `VERIFIED` label을 갖지만 50개 subset만 담는다.
실제 ID 묶음은 `I-A 01–16`(16), `I-C 17–23`(7), `II-A 01–14`(14),
`II-B 01–12`(12), `II-C 01`(1)이다. `reviewed_manifest_001_080.json`은 여기에
`II-C 02–23`(22)와 `III-A 01–08`(8)을 더한 80개 subset이다. 두 reviewed 파일 모두
Step B의 `-1` 변형 ID를 포함하지 않는다. 따라서 50/80은 source 전체 371과 각각
동일하지 않다.

v6 `고등수학하_미주작업_완료.hwpx`(SHA-256
`2b2c91249987bdc39d4f09f802e54f8d3f843c3e6551abcfa7ab4230ea567fb3`)는 ZIP/XML 정적
검사에서 `hp:endNote` 50개와 `numType=ENDNOTE` 50개를 포함한다. 따라서 v6는
개수상 `001_050` subset에 해당하며, 80-item reference와는 일치하지 않는다.
XML의 인쇄번호 문자열만으로 source ID 대응 또는 fidelity를 확정하지 않는다.

## 재사용 validator

`app/pdf_hwp_scope_reconciliation.py`의 `materialize_candidate_items()`는
`items`형 후보와 `pages`형 후보를 동일한 ID 집합으로 정규화한다. pages형에서는
Step B base/`-1` 확장을 적용하고 page-level declared count와 확장 count의 불일치를
진단한다. `reconcile_manifests()`의 `scope_assessment`는 다음을 분리한다.

- `candidate_item_count`
- `reviewed_candidate_item_count`
- `unreviewed_candidate_item_count`
- `coverage_ratio`
- `scope_classification` (`PARTIAL_SCOPE` 등)
- `full_book_release_eligible` (항상 `false`)

검증:

```text
python -m pytest tests/test_pdf_hwp_scope_reconciliation.py tests/test_math_content_scope.py -q
21 passed
```

이 validator는 metadata reconciliation 도구다. `VERIFIED` label, endnote 개수,
manifest count equality만으로 source fidelity PASS를 만들지 않는다.
