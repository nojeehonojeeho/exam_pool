# 원문 충실도 v2 합성 회귀 검증 명세

공통 실행 기본값은 [사용자 의도 기반 실행 기본값](USER_INTENT_EXECUTION_DEFAULT.md)을
적용한다. 회귀 검증 요청이 명확하면 계획만 남기지 않고 안전한 테스트·기록까지 수행한다.

상태: **설계 명세 반영. 아래 항목의 테스트 구현·실행 완료를 뜻하지 않는다.**
적용 계약: [원문 충실도 v2 작업지시서](PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md).
기존 테스트는 유지하고 다음 구현 요청에서 미지원 항목을 보강한다. 아래 식별자는
테스트 요구 ID이며, 현재 코드에 같은 이름의 FAIL code가 있다는 뜻이 아니다.

## 공통 조건

- 실제 교재 문장·문항·도형·PDF·HWP·전사 원장은 fixture로 사용하지 않는다.
- 독자적으로 만든 짧은 합성 문항, 표, 도형, 수식과 정상/손상 쌍을 사용한다.
- 원문→검수 원장과 검수 원장→출력 검사를 분리한다. 둘 다 같은 잘못된 전사에서
  생성한 expected/actual이면 독립 원문 검증이 아니다.
- unit/순수 XML 테스트, 실제 production runner 통합 테스트, 한글 설치 환경의
  COM·재열림·렌더 테스트를 구분한다. 환경 부재의 skip은 PASS가 아니다.
- 문법적으로 유효하지만 의미가 틀린 사례를 포함한다. 개수만 같은 잘못된 문서를
  정상으로 인정하지 않는지 확인한다.

## A. 내용·범위·작성 경로

| ID | 손상 사례 → 요구 결과 | 정상 대조군 |
|---|---|---|
| C01 | 주관식 원문에 없는 선지 생성 → FAIL | 원문 근거가 있는 선지 0개 |
| C02 | 해설 정답/인접 문제 선지가 문제에 혼입 → FAIL | 문제와 해설의 역할 분리 |
| C03 | 문제 안 빈칸 풀이·증명 삭제 또는 답 기입 → FAIL | 빈칸/풀이 공간 그대로 보존 |
| C04 | OCR 행마다 강제 문단/조사·어절 파손 → FAIL | 완전한 의미 문단의 정상 자동 줄바꿈 |
| C05 | 조건·질문·선지·후속 문장 순서 변경/중복 → FAIL | 원문 읽기 순서와 각 필드 1회 소비 |
| C06 | text wrapper의 condition/question/table/choices를 조용히 무시 → FAIL | 명시적 정규화와 저장/readback 추적 |
| C07 | unknown 내용 key를 metadata로 간주해 버림 → FAIL | 별도 허용 metadata namespace |
| C08 | 선언 개수는 일치하지만 실제 작성 blocks/셀 일부 누락 → FAIL | 실제 writer 입력 및 출력에서 확인 |
| C09 | 여러 inline run을 임의 문단으로 분리 → FAIL | 명시적 일대다 매핑 후 내용·순서 재결합 |
| C10 | 혼합 페이지 개념 영역 유입/포함 문제 영역 누락 → FAIL | 검수된 region 집합 정확히 일치 |
| C11 | 부분 변환을 전체 책 쪽수와 비교/제외 쪽을 재삽입 → FAIL | source-region→output 대응표 |
| C12 | 인쇄 번호·PDF 쪽·전역 순번 혼용/반복 번호 오연결 → FAIL | 안정적 item ID 및 내용 증거 |
| C13 | 원장이 없는 상태를 원본 부재로 판정 → 검수 큐, writer 차단 | 원본 확인 후 실제 검수 원장 작성 |

## B. 수식 구조·개체·경계

| ID | 손상 사례 → 요구 결과 | 정상 대조군 |
|---|---|---|
| M01 | sum/prod 본체·상하한 소실/다른 연산자에 결합 → FAIL | 원문 구조와 범위 보존 |
| M02 | limit 접근값/좌우 조건, integral 한계/미분기호 변경 → FAIL | 각 구조 필드 일치 |
| M03 | 첨자 소유 대상·중첩·분수·근호 범위 변경 → FAIL | 동일 AST 구조 및 렌더 |
| M04 | cases 조건/행, matrix 차원, vector/좌표 성분 변경 → FAIL | 행·열·조건·기호 소유권 보존 |
| M05 | 팩토리얼+등호를 NotEqual로 컴파일 → FAIL | Factorial과 Equal 분리 |
| M06 | 실제 NotEqual을 팩토리얼+등호로 일괄 치환 → FAIL | dialect에 맞는 NotEqual 출력 |
| M07 | 연산자 접두부만 변환하고 나머지를 영문 변수로 출력 → FAIL | 닫힌 operator mapping과 실제 렌더 |
| M08 | 네이티브 식 대신 평문/이미지 또는 빈 script → FAIL | 수정 가능한 실제 수식 |
| M09 | 같은 개수지만 소유 문항·표 셀·순서가 다름 → FAIL | occurrence ID/owner/order/readback 일치 |
| M10 | AST 중첩 노드 수를 개체 수로 사용/임의 분리·병합 → FAIL | 고정된 occurrence 단위의 연쇄 검사 |
| M11 | crop hash와 VERIFIED만 있고 실제 대조 내역 없음 → UNVERIFIED | 원본 연결 검수 내역과 불확실성 0 |
| M12 | 저장 전은 정상, HWP 또는 재열림 script가 변경 → FAIL | HWP/HWPX/COM 전후 script 보존 |
| M13 | 네이티브 equation 뒤 `hp:t`에 `\\bar`, `\\sum`, `\\lim` 등 수식 명령이 남음 → FAIL (`FORMULA_RAW_BACKSLASH_TEXT`) | 수식 위치에 native equation만 있고 표시 텍스트에는 raw command가 없음 |

## C. 서식·배치·그림

| ID | 손상 사례 → 요구 결과 | 정상 대조군 |
|---|---|---|
| L01 | source_region 모드에서 공통 B4/첫 쪽 규격 전체 강제 → FAIL | 페이지별 원문 규격 |
| L02 | HWP 용지와 축소 PDF 출력 용지를 혼동 → FAIL | 물리 배율·용지 기록과 동일 배율 비교 |
| L03 | 1×2 wrapper 표를 native 2단으로 집계 → FAIL | 실제 어댑터 종류와 흐름 시험 |
| L04 | 스타일 정의만 정상이고 실제 text run/유효 switch 분기가 다름 → FAIL | 유효 속성 및 COM readback |
| L05 | 원문 글꼴 unknown을 measured로 보고 → FAIL | 편집용 선택값과 측정값 구분 |
| L06 | 의도된 답안 공간을 large-gap으로 자동 삭제 → FAIL | 근거 있는 blank/workspace 보존 |
| L07 | 좁은 표/단에서 잘림·겹침·과도한 justify·보기 순서 역전 → FAIL | 전체 페이지 객체·시각 대조 |
| G01 | 그림 설명문만 있고 실제 그림 없음 → FAIL | 실제 네이티브 도형/허용 순수 crop |
| G02 | crop 내부 라벨·선 끝 누락 또는 다른 문항 그림 → FAIL | bbox·잉크 경계·소유권 확인 |
| G03 | 테두리는 있으나 내부 표/병합/셀 내용 누락 → FAIL | 표 구조·내용·읽기 순서 일치 |
| G04 | 본문/수식/문항 페이지 캡처로 외관만 재현 → FAIL | 직접 편집 텍스트/수식/표 |
| G05 | package preview를 본문 이미지로 오분류 → 오탐 금지 | 실제 본문 참조와 메타 자원 분리 |
| G06 | 작은 면적의 풀이 캡처라서 허용 → FAIL | 면적과 무관한 내용 분류 |

## D. 상태·증거·미주·출고

| ID | 손상 사례 → 요구 결과 | 정상 대조군 |
|---|---|---|
| R01 | XML/style/build PASS를 release PASS로 복사 → FAIL | 모든 필수 독립 게이트 증거 |
| R02 | REVIEW_REQUIRED/pending/source_fidelity=false 후처리 승격 → FAIL | 미완료 상태 유지 |
| R03 | 원본/scope/원장/profile/code/output 변경 뒤 옛 QA 재사용 → FAIL | 영향받는 게이트 재검증 |
| R04 | 테스트된 라이브러리를 실제 builder가 호출하지 않음 → 미연동 | 실제 ordered input→저장→QA 통합 증거 |
| R05 | 출고/압축 파일과 검수 파일 hash가 다름 → FAIL | 파일별 동일 hash |
| R06 | 동일 hash 기존 파일을 현재 계약으로 재검수해 재제공 → 허용 | 재제공 이력 명시, 날짜만으로 오탐 금지 |
| R07 | 필수 게이트를 N/A로 숨김/문제 전용 요청에 미주 강제 → FAIL | 요청 기반 applicability와 미주 0 확인 |
| E01 | 반복 번호 문항의 해설 교환, 미주 존재하나 일부 풀이 누락 → FAIL | ID/내용 fingerprint/전수 대응 |
| E02 | 미주 본문·정답·수식 이미지 또는 수식 평문 대체 → FAIL | 네이티브 본문·식·표, 허용 그림만 |
| E03 | 미주 삽입 후 문제/해설 체크포인트 내용 변경 → FAIL | 전후 독립 내용 snapshot |
| E04 | 재열림/복사·이동 시 미주 소실·오연결 → FAIL | 검사용 사본의 실제 COM/편집 시험 |
| E05 | 일부 체크포인트를 미검수 전체본과 병합해 최종 표시 → FAIL | 전체 범위 및 통합본 재감사 |
| E06 | 문제 본문과 해설 미주가 섞이거나 문서 끝 이외에 렌더 → FAIL | 문제 본문 선행 + `END_OF_DOCUMENT` native 미주 |

## 구현 완료 보고 조건

각 요구 ID에 실제 테스트 경로·테스트명, 실행 명령, 실행 환경, 결과를 연결한다.
단위 테스트 통과는 실제 교재의 원문 충실도 증명이 아니다. 실제 진입점의 합성 통합
실행과 COM/렌더 시험이 남으면 해당 층은 미완료로 보고한다. 실제 교재 제작은 별도
승인된 작업에서 수행하고, 원문 검수 및 산출물 증거는 저장소 밖 로컬에 둔다.

## E. 진행률과 root-cause 회귀

| ID | 입력 | 기대 결과 |
|---|---|---|
| RC01 | 106개 중 22개만 evidence closed | `scope_item_count=106`, `evidence_closed_item_count=22`, `evidence_open_item_count=84`; 제작 문항 수로 해석하지 않음 |
| RC02 | 한 원인에서 4개 raw finding 발생 | raw finding 4건을 보존하고 후보 원인 1건으로 진단 집계하되 release blocker는 4건으로 유지 |
| RC03 | 서로 다른 수식·표·그림 오류가 같은 문항에 존재 | semantic anchor가 달라 각각 별도 root cause 후보로 유지 |
| RC04 | root-cause grouping 후 재검증 | 동일 input hash·policy version의 strict 재실행에서 raw finding이 실제 감소한 경우에만 해결로 기록 |
| RC05 | grouping이 모든 finding을 병합 | 테스트 실패; 자동 PASS·finding 삭제·N/A 변환 금지 |

`root_cause_id`는 진단용 후보이며 `candidate_only=true`, `resolved=false`를 기본값으로
한다. 최종 release gate는 raw finding과 evidence-open 문항을 직접 검사한다.

### 네이티브 미주 문서 끝 배치 회귀

`tests/test_endnote_qa_gate.py`는 HWPX의 `footNotePr`와 `endNotePr`를 구분하여
검사한다. 유효한 fixture에서는 `hp:endNotePr/hp:placement/@place`가
`END_OF_DOCUMENT`이고, `EACH_COLUMN` 또는 placement 누락 fixture에서는 각각
`ENDNOTE_PLACEMENT_INVALID`·`ENDNOTE_PLACEMENT_UNDECLARED`로 실패해야 한다.
이 단위 회귀는 실제 한글 재열림·렌더·복사/이동 시험의 대체물이 아니며, 실제 통합본
출고에서는 본문 문제 순서·미주 body 순서·1:1 reference와 COM 결과를 추가로 확인한다.

`tools/audit_integrated_endnote_layout.py`(schema `integrated-endnote-layout-audit-v2`)와
`tests/test_integrated_endnote_layout.py`는 통합본 후보의 문서 끝 배치 계약을 별도로
고정한다. 이 감사기는 (a) 문제 본문에 해설 표식이 누출되지 않았는지, (b) 모든 native
미주 body가 비어 있지 않은지, (c) 미주가 있는 section의 placement 누락과 모든 선언된
`endNotePr`의 비문서끝 값을 실패시키는지, (d) 네 과목
`고등수학상·고등수학하·수학II·확률과_통계`가 모두 존재하고 각 HWPX에 HWP 쌍이 있는지를
검사한다. 입력 경로 오류도 예외를 내보내지 않고 구조화된 FAIL로 반환해야 한다. 이
감사기는 구조 후보 게이트이며 원본 PDF 대조·COM 재열림·전 페이지 시각검수를 대체하지
않는다.

### 실행 보고기 회귀

`tests/test_v2_execution_report.py`는 실행 원장에 대해 다음을 고정한다.

| 케이스 | 기대 결과 |
|---|---|
| strict ledger와 closure summary가 함께 있음 | ledger 행 수를 raw finding으로 보고하되 closure의 release blocker는 별도 보존 |
| legacy `VERIFIED`만 있고 v2 closure가 없음 | legacy pass로 승격하지 않고 v2 evidence-open으로 집계 |
| `evidence_open_item_count=0`이지만 raw/release blocker가 남음 | `FINAL_PASS` 금지 |
| 모든 독립 수량과 production build가 PASS | `FINAL_PASS` 허용 |

| RC06 | 기존 subset만 VERIFIED_SUBSET이고 전체 범위가 열려 있음 | subset은 checkpoint로만 기록하고 전체 release PASS로 승격하지 않음 |
| RC07 | source/manifest/code hash 변경 | 관련 evidence closure와 이전 QA를 무효화하고 재검수 큐에 넣음 |
| RC08 | 수식 개수는 같지만 순서·소유 문항·표 셀이 다름 | occurrence ID/owner/order 비교에서 FAIL |
| RC09 | 하위 finding status를 수동 변경 | strict 재실행에서 실제 소거되지 않으면 OPEN 유지 |
| RC10 | HWP가 열리고 XML이 정상 | SourceFidelity·NativeEditability·EndnoteLinkage 독립 게이트 없이는 PASS 금지 |
| RC11 | checkpoint status가 `CHECKPOINT_VERIFIED_NOT_BOOK_FINAL` | `candidate_only=true`, `evidence_closed_item_count` 불변, release PASS 금지 |
| RC12 | checkpoint manifest hash·600/900dpi·작성기 수식 수·ZIP 무결성 중 하나가 누락/변경 | 해당 checkpoint를 재사용 후보에서 제외하고 원인 목록을 보존 |
| RC13 | candidate-only 원장을 부모 전체 원장에 연결 | 최신 v2 strict 재실행 전에는 evidence-open 감소·raw finding 삭제·PASS 승격 금지 |
| RC14 | 과거 검토 범위가 80개이고 전체 범위가 371개 | `legacy_reviewed_scope_count=80`은 참고값일 뿐이며 최신 v2 재검증 결과로 `evidence_closed_item_count`·`evidence_open_item_count`를 다시 계산 |
| RC15 | “291개 미검수”를 고정값으로 보고 | 291을 코드·보고서에 하드코딩하지 않고 매 실행 실제 `evidence_open_item_count`를 산출 |
| RC16 | raw finding·root cause·blocking item·release blocker를 혼동 | 네 필드를 각각 기록하고 root-cause 감소만으로 PASS하지 않음 |
| RC17 | root-cause 키가 실행마다 달라짐 | `document_role|item_id|stage|evidence_key|source_hash` 정규화 키로 결정적으로 재생성 |
| RC18 | source/manifest/crop/compiler/writer/code hash 변경 후 이전 closure 재사용 | 관련 closure와 이전 QA를 무효화하고 해당 문항을 evidence-open 큐에 재투입 |
| RC19 | 문제 번호순 단일 큐로 복잡 문항 처리 | source page/region·단원·문서 역할·formula root cause·특수 블록별 배치 큐를 생성하고 각 항목을 `release_eligible=false`로 시작 |
| RC20 | writer syntax PASS를 source fidelity PASS로 오인 | strict runner가 per-formula provenance gate를 writer/COM 전에 실행하고 source evidence·MathIR·dialect 누락 시 BLOCKED |
| RC21 | formula count가 같다는 이유로 원본 수식 연쇄를 생략 | occurrence ID·소유 문항·순서·600/900dpi crop/bbox·MathIR hash·dialect script를 1:1로 검사 |
| RC22 | item-level source evidence를 모든 수식의 증거로 재사용 | typed formula block 또는 flat occurrence ledger에 formula-level evidence를 요구하고 item-level metadata만으로는 PASS 금지 |
| RC23 | source/authoring 수식 occurrence를 fuzzy·페이지 근접으로 연결 | `pdf_hwp_formula_closure`는 명시적 ID exact match를 우선하고, 양쪽 ID가 없을 때만 유일한 item/order/source-hash composite match 허용 |
| RC24 | source ID와 다른 authoring ID를 composite key로 우회 | `FORMULA_AUTHORING_OCCURRENCE_ID_MISMATCH`와 link missing을 함께 기록하고 `REVIEW_REQUIRED` 유지 |
| RC25 | closure ledger의 item-level crop을 formula-level 증거로 상속 | 수식별 bbox/crop SHA-256/DPI가 직접 없으면 source review open으로 유지 |

| RC26 | 후보 ID 수와 선언 항목 수를 하나의 문항 수로 보고 | 두 값을 분리하고 차이의 원인을 기록; 실제 출고 범위는 원본 대조 후 확정 |
| RC27 | Step B의 기본 번호만 후보 ID로 생성 | 원본에 `n`·`n-1`이 함께 있으면 두 개의 고유 ID와 별도 해설 대응으로 확장 |
| RC28 | 레거시 `VERIFIED` 또는 출력 ID 존재를 evidence closure로 승격 | 문항별 PDF hash·페이지·bbox·crop hash·review ID가 있는 `evidence_status=CLOSED`만 closure |
| RC29 | 승인창 열거 실패를 승인창 0회로 집계 | `WINDOW_ENUMERATION_UNAVAILABLE`로 차단하고 조회 성공 증거 없이는 COM PASS 금지 |
| RC30 | 전역 보안 프로브의 0회 결과를 문서별 COM 재열림 증거로 재사용 | 문서별 각 Open/SaveAs 관찰을 `approval_observations[]`로 기록하고, 12행 모두 `status=OK`, 빈 `titles[]`, 합집합 `approval_window_count=0`일 때만 `com_provenance_closed=true` |
| RC30 | 최초 Hwp PID만 종료 확인하고 재열림 PID를 누락 | 생성·재열림·출력 단계의 모든 소유 PID와 단계별 deadline을 기록하고 전부 종료 확인 |

### 범위·세션 회귀 테스트

`tests/test_pdf_hwp_scope_reconciliation.py`는 후보 ID 수, 선언 항목 수, 레거시 검토
수, 명시적 evidence closure 수, 열린 ID 수를 분리한다. `review_status=VERIFIED`만
있는 문항은 legacy scope로만 집계하고 `final_eligible=false`로 유지한다. Step B
페이지의 기본/변형 번호는 `expand_step_b_variants()`로 각각 생성한다. 또한 후보·검토
iterable이 generator여도 중복 순회로 closure가 사라지지 않아야 한다.

COM 재열림 회귀(`tools/hwp_com_security_serial_probe.py`)는 `RegisterModule=True`, 승인창 열거 성공, 파일 저장·재열림·PDF 출력,
최초 및 재열림 Hwp PID 종료가 모두 증거로 남아야 PASS로 인정한다. COM을 생략한
XML-only 결과는 구조 회귀가 통과해도 `reopen_pass=false` 상태를 유지한다.

### 수식 provenance gate 합성 회귀

`tests/test_pdf_hwp_formula_provenance_gate.py`는 다음을 고정한다.

| 케이스 | 기대 결과 |
|---|---|
| script만 있고 source evidence/MathIR 없는 수식 | `FORMULA_OCCURRENCE_ID_MISSING`, `FORMULA_SOURCE_EVIDENCE_MISSING`, `MATHIR_MISSING`으로 FAIL |
| page+bbox+600/900dpi crop hash+source PDF hash+MathIR hash+dialect가 모두 일치 | 해당 수식 provenance PASS |
| MathIR source hash 또는 crop hash 변조 | 각 gate의 독립 FAIL 유지 |
| 동일 occurrence ID를 두 블록이 공유 | `FORMULA_OCCURRENCE_ID_DUPLICATE`로 FAIL; raw findings 삭제 금지 |

### 수식 closure 합성 회귀

`tests/test_pdf_hwp_formula_closure.py`는 다음을 고정한다.

| 케이스 | 기대 결과 |
|---|---|
| 명시적 source/authoring occurrence ID가 동일하고 provenance가 완비됨 | `PASS`, `closure_status=CLOSED` |
| 양쪽 occurrence ID가 없고 유일한 item/order/source-hash만 일치 | `exact_composite_key`로 연결하되 다른 gate는 별도 통과 필요 |
| source ID가 있는데 authoring ID가 다른 경우 | `FORMULA_AUTHORING_OCCURRENCE_ID_MISMATCH` + `FORMULA_AUTHORING_LINK_MISSING`, `REVIEW_REQUIRED` |
| authoring MathIR 또는 dialect가 없음 | `FORMULA_AUTHORING_MATHIR_MISSING` 또는 `FORMULA_AUTHORING_DIALECT_MISSING`, `candidate_only=true` |
| item-level evidence에만 bbox/crop이 있고 formula record에는 없음 | formula geometry를 닫지 않고 `FORMULA_SOURCE_REVIEW_OPEN` |

### HWPX visible-text formula fallback 회귀

`tests/test_hwp_delivery_reaudit.py::test_audit_hwpx_rejects_raw_backslash_in_visible_text`
는 native equation과 같은 문단의 `hp:t`에 `\\bar{X}`가 남은 합성 HWPX를
`FORMULA_RAW_BACKSLASH_TEXT`로 실패시키는지 고정한다. 검사기는 section/endNote의
직접 문단 텍스트를 한 번만 집계해야 하며, nested table 조상 순회로 같은 finding을
부풀리지 않는다. 실제 자료에 이 finding이 있으면 repair 후 source crop·MathIR·
COM 재열림·렌더를 재검증하고, 수리 전 산출물을 최종본으로 승격하지 않는다.

실행 산출물에는 `strict-findings.jsonl`, `root-cause-summary.json`,
`evidence-closure-summary.json`, `formula-occurrence-ledger.jsonl`,
`problem-solution-linkage.json`, `work-queue.json`, `build-and-qa.json`,
`EXECUTION_STATUS.md`가 있어야 하며, 각 산출물은 입력·manifest·코드 hash를 기록한다.
공통 실행 기본값은 [사용자 의도 기반 실행 기본값](USER_INTENT_EXECUTION_DEFAULT.md)을
적용한다. 회귀 검증 요청이 명확하면 계획만 남기지 않고 안전한 테스트·기록까지 수행한다.
