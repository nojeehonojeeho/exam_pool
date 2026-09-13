# 최초 요청부터 v12까지: 요구·실패·재발 방지 추적표

2026-09-13 · 기준 `math-pdf-native-hwp-v12/1.0.0`

[공통 실행 원칙](USER_INTENT_EXECUTION_DEFAULT.md)과
[단일 요청 기본 지시서](PDF_HWP_V12_ONE_REQUEST_WORK_INSTRUCTIONS.md)를 적용한다.
분석 근거는 현재 대화에 제공된 최초 요구/반복 피드백, 저장된 정밀감사·인계 기록,
v11/v12 구조·COM·경계 기록 및 현재 저장소 코드다. 과거 모든 파일의 원문 내용이나
누락된 미저장 대화를 이번에 전수 재검증했다는 뜻은 아니다.

## 1. 왜 여러 번 다시 만들게 되었는가

| 단계/피드백 묶음 | 실제 문제 유형 | 반복을 막는 기본 절차 |
|---|---|---|
| 최초 기준 HWP 서식 요청 | 측정한 프로필과 선택한 서식, 원본 배치가 혼용됨 | 원문 기하/편집 프로필 분리·실제 run/문단 속성 검사 |
| 시그마부터 극한/cases까지 수식 손상 | OCR 문자열·수식 개수와 원문 구조를 동일시함 | occurrence별 원문→MathIR→native 저장/readback |
| 문장 분할·띄어쓰기·보기 오류 | OCR 행/정규식을 문단으로 사용; writer가 일부 필드를 버림 | 의미 문항 IR·닫힌 schema·실제 필드 소비 원장 |
| 좋은 1~6번 외관 시험 | 전체 페이지 이미지 기반 외관과 직접 편집성을 혼동함 | 외관+실제 text/equation/table 편집을 함께 통과 |
| 문제 없는 개념 쪽까지 포함 | 전체 책 OCR 뒤 제거·페이지 단위 문항 추정 | 포함 문제/해설 영역을 OCR 전에 확정 |
| 문제-해설 누락/오연결 | 인쇄 번호/순번/분할 개수만으로 연결 | 단원·변형·반복 번호·연속 영역·내용으로 stable ID |
| 후보를 완료본처럼 제공 | 구조 PASS/파일 생성/과거 VERIFIED를 FINAL로 승격 | 독립 source/technical/layout/linkage/release 판정 |
| COM 고착/앱 재시작 | 실제 보안 등록·호출 timeout·소유 PID·체크포인트 부족 | 공통 secure helper·직렬 감독·유한 재시도·증거 재사용 |
| v10/v11 미주 위치 피드백 | END_OF_DOCUMENT 설정만으로 새 물리 페이지를 추정 | 모든 문제 선행+첫 미주 새 페이지를 독립 렌더 검사 |
| v12 수용 | 원하는 문서 흐름의 사용 기준이 확보됨 | 배치/편집 패턴을 일반화하되 기존 전사/부분 범위는 새 정답으로 고정하지 않음 |

## 2. 요구사항별 누락 방지표

아래 ‘연결’은 구현/증거를 확인할 지점이다. **링크가 있거나 단위 테스트가 통과했다는
이유만으로 모든 제작 경로에 구현됐다고 선언하지 않는다.** 새 작업의 S0에서 실제
runner/writer/packager 호출 연결을 기록하고, 미연동 경로는 구현 후 사용한다.

| ID | 사용자 요구 또는 과거 실패 | 필수 조치/실패 조건 | 연결 |
|---|---|---|---|
| V12-01 | 실제 기준 HWP 서식을 추출 | char/para/page 등 7군 측정·프로필 이름/버전/해시; 추정은 measured 아님 | `MATH_HWP_REFERENCE_STYLE_WORK_INSTRUCTIONS.md` |
| V12-02 | 별도 사용자 서식 우선, 없으면 기본 | source layout과 editable style 분리; 기본/사용자 지정 적용 여부 보고 | 기본 지시서 §5 |
| V12-03 | 숫자·기호·script·표 셀·그림 연결·ID 불변 | 서식 보정 전후 content snapshot; 변경이면 교정 개정판과 근거 필요 | `app/hwpx_content_snapshot.py` |
| V12-04 | 문제 있는 영역만 제작 | 전체 페이지 역할 조사, 포함/제외 bbox; 개념/표지 전체 OCR 금지 | `MATH_PDF_CONTENT_SCOPE_AND_ENDNOTE_MAPPING.md` |
| V12-05 | 해설 색인으로 문제 범위 역추적 | PDF 물리/인쇄/출력 쪽과 문항 순번 별도 기록 | 기본 지시서 §3 |
| V12-06 | 기본·변형·반복 번호 누락 금지 | source 근거 있는 stable ID; 선언 수=실문항 수로 간주 금지 | `tests/test_pdf_hwp_scope_reconciliation.py` |
| V12-07 | 문제와 대응 정답/전체 풀이 | 단원/내용/bbox/continuation; zip·round-robin·절반 분할 금지 | 기본 지시서 §3, §9 |
| V12-08 | 원문 해설이 없으면 창작 금지 | 문제 작업은 계속, 해설 없는 상태 명시; AI 풀이 별도 요청 필요 | 기본 지시서 §3 |
| V12-09 | OCR 손상 직접 대조 | 포함 영역 600dpi, 고위험 900dpi, 실제 열람/해시/불확실성 | `PDF_HWP_MATH_FORMULA_SOURCE_REVIEW.md` |
| V12-10 | anydoc와 초기 converter 누락 방지 | 보조 후보 역할·버전·strict wrapper·전송 권한; 직접 정답으로 사용 금지 | `OCR_HYBRID_CONVERTER_ANYDOC_WORK_INSTRUCTIONS.md` |
| V12-11 | 한 문장을 쪼개지 않기 | OCR 행≠문단; inline run/조사/어절 복원, 정상 자동 줄바꿈 허용 | `tests/test_source_block_contract.py` |
| V12-12 | 띄어쓰기·과도한 양쪽 벌림 수정 | 실제 유효 paraPr/charPr와 원문 대조; 전역 공백 제거/삽입 금지 | `PDF_HWP_SEMANTIC_RECONSTRUCTION_BASELINE.md` |
| V12-13 | 주관식에 가짜 선지 추가 금지 | 원문 근거 expected_choice_count=0, 다른 문제/해설 선지 혼입 차단 | `app/hwp_authoring_preflight.py` |
| V12-14 | 보기·조건·질문·후속 문장 누락 금지 | 실제 writer 소비 ledger, 닫힌 schema, unknown/ignored content FAIL | 원문 충실도 v2 §4, §12.14 |
| V12-15 | 선지 배치·네이티브 표 | 원문 행열·셀 내용/병합/읽기 순서; 표를 이미지로 대체 금지 | 기본 지시서 §5 |
| V12-16 | 시그마/곱의 상하한 | 본체·상/하한 소유 구조; 예외는 원문 특정 occurrence만 | `app/pdf_hwp_formula_provenance_gate.py` |
| V12-17 | 극한/적분 접근조건·범위 | 변수·접근값·좌우 방향·상하한·미분기호 전수 | 원문 충실도 v2 §6 |
| V12-18 | 첨자·분수·근호·cases·행렬·벡터 | 중첩 소유/범위/차원/조건 행과 native 렌더 대조 | `tests/test_hwp_equation_compiler.py` |
| V12-19 | 팩토리얼/등호·집합·조합 오독 | dialect별 의미 분리, raw LaTeX 잔재·일괄 != 치환 금지 | 원문 충실도 v2 §6, §12.18 |
| V12-20 | 수식 개수만 맞추는 검사 금지 | occurrence ID/owner/cell/order/AST/script 연쇄; 수식 없는 문항도 검수 | `app/pdf_hwp_formula_closure.py` |
| V12-21 | 긴 식과 prose 수식 혼입 | source MathIR 불변·표시용 줄 계획·prose는 editable text | `tests/test_hwp_equation_line_layout.py` |
| V12-22 | 그래프·그림 실제 보존 | 순수 crop/네이티브 도형·owner/hash; 설명문/페이지 캡처 대체 FAIL | 원문 충실도 v2 §7, §12.13 |
| V12-23 | 기준 용지/단/원본과 다른 배치 | source-region/편집 reflow 계약 구분; 첫 페이지/중앙값 전체 강제 금지 | 기본 지시서 §5 |
| V12-24 | 잘림·고아 문장·큰 공백 | 검토된 작은 keepWithNext 묶음·수식 너비·표 너비; 의도된 풀이 공간 보존 | 원문 충실도 v2 §12.11–§12.21 |
| V12-25 | 변환과 미주 한 번에 요청 | S0–S7 내부 체크포인트, 반복 중간 승인 없이 이어가기 | 기본 지시서 §7 |
| V12-26 | 모든 문제 먼저, 해설은 마지막에 | 주 본문 문제만·native reference/body 1:1, 본문 solution leakage FAIL | `tests/test_endnote_qa_gate.py` |
| V12-27 | 마지막 문제 다음 새 쪽에서 첫 해설 | 독립 마지막 문제 끝/첫 note page·빈 gap/같은 쪽 금지 | `tests/test_hwp_first_native_endnote_page_break.py` |
| V12-28 | 53쪽 등 특정 기존 값 일반화 금지 | 실제 새 문항/출력 경계 측정; heading쪽-1 역산·부분 문자열 오판 차단 | boundary audit v2 |
| V12-29 | 문제 복사시 해설도 함께 따라오기 | 실제 editor 선택 reference·별도 문서 복사/이동·저장/재열림 | `tools/hwp_native_endnote_transfer_probe.py` |
| V12-30 | 미주 전후 같은 내용 | 문제/풀이/통합 같은 content revision, source→IR와 IR→출력 검사 분리 | `app/hwpx_content_snapshot.py` |
| V12-31 | 실제 HWP·HWPX 두 형식 | 두 포맷 직렬 저장/닫기/재열림·개체 readback, 확장자 이름만 변경 금지 | `tools/hwp_serial_readback.py` |
| V12-32 | 승인창 반복 중단 해결 | 공식 Automation DLL·비트수/HKCU·RegisterModule 실제 True; 조회 실패≠0회 | `HWP_COM_AUTOMATION_SECURITY.md` |
| V12-33 | COM 무한 고착·프로세스 증식 방지 | 직렬 잠금·모든 소유 PID·호출 deadline·정상 종료·원인 수정 재시도1회 | 원문 충실도 v2 §12.10 |
| V12-34 | 메모리/CPU 부하·에이전트 제한 | 읽기 전용 부하 진단·70%시 투입 감소, 작업 중 프로세스 강제 종료 금지 | 기본 지시서 §10 |
| V12-35 | 앱 종료후 기록 보존/재개 | 원본/원장/산출물 hash·진행 단계 보존; 유효 증거 영향 범위만 재검수 | 기본 지시서 §10 |
| V12-36 | raw findings와 진짜 오류 혼동 금지 | scope/reconstructed/legacy/closed/open/delivered·root cause 별도 | `tests/test_v2_execution_report.py` |
| V12-37 | 구조 PASS를 원본/FINAL로 보고 금지 | 전체 원문·전 페이지·COM·미주·출고 증거 별도, OPEN 상태 조작 금지 | `PDF_HWP_RELEASE_GATING_WORK_INSTRUCTIONS.md` |
| V12-38 | 실제 출고 폴더 파일·압축 정확성 | 과목별 전체 3역할×2형식, 문항별/QA 파일 별도, 제공후 hash 대조 | 기본 지시서 §11 |
| V12-39 | 현실적 최대 품질 후보 제공 | 사용자 수용 상태와 whole-source FINAL 분리, 누락/미검수 범위 명시 | 기본 지시서 §1, §11 |
| V12-40 | 지시서·코드·테스트·GitHub 갱신 | 요구/회귀/실제 호출 연결 확인; fork/origin 구분; 저작권 자료 git 제외 | 기본 지시서 §2, §11 |
| V12-41 | 내부 검수/진단 문구 유출 금지 | body/endnote/caption과 metadata 분리, 발견후 내용 보존 교정 | `app/hwp_delivery_reaudit.py` |
| V12-42 | 다음 실행 모드 선택 | Luna max 표준 기본, Astra xhigh는 허용된 난제 감사; 품질은 증거로 판단 | 기본 지시서 §12 |

## 3. 이번 정리에서 확인한 지침 충돌과 조치

- v2 §5의 페이지별 기하와 §12.2의 첫 페이지/중앙값 전체 적용이 충돌했다.
  일괄 도구는 같은 규격인 경우로 제한하고 혼합 규격은 페이지별 adapter로 분기한다.
- ‘미주는 별도 요청’이라는 옛 문구는 한 번에 변환+미주를 요청한 현재 기본과
  혼동될 수 있다. **요청은 한 번, 내부 단계/검수는 별도**로 정리한다.
- solution box를 모두 포함한다는 옛 문구는 무관한 일반 개념을 제외하라는 범위
  정책과 충돌했다. source owner·문항별 관련성에 따라 포함 원장을 만든다.
- HancomEQN은 구형 converter 후보 단계 계약에 남아 있다. 새 출고 프로필의
  HYhwpEQ와 혼동하지 않는다. 후보 성공을 최종 폰트 적용 증거로 사용하지 않는다.
- 문항 전체 keepWithNext 고정은 긴 문항에서 과대 공백을 만들 수 있다. 실제 높이와
  원문 의미 경계로 최소 필요한 묶음만 보호한다.
- 과거 단일 실행 Astra low 오버라이드는 실행 ID에만 적용한다. 향후 기본 모델을
  바꾸지 않으며, 실제 선택 모델은 실행 기록으로 확인한다.
- COM 세션 이후 모든 검사를 ‘처음부터’ 반복하라는 옛 문장은 의존성 해시 재사용
  원칙과 충돌했다. 저장/재조판 변경의 실제 영향 범위만 다시 검사한다.
- boundary v1은 첫 미주 제목 쪽−1을 마지막 문제 쪽으로 추정했고, 짧은 제목의
  부분 문자열도 일치했다. v2는 독립 검수 기록·실제 입력/PNG 해시를 요구한다.
  이 보강은 `hwp_release_gate`와 `require_final_release` 경계에도 연결한다.

## 4. v12에서 가져오는 것과 가져오지 않는 것

기존 기록의 native 미주 수는 과목별 106/60/76/50이고, v12 변경 대상은 네 통합본
HWP/HWPX 8개였다. 문제·별도 풀이 파일은 이전 개정판에서 유지된 파일이다.
이 숫자는 현재 **출력 관찰 범위**이며 각 원본 전체 문제 수로 일반화하지 않는다.

재사용: native 문서 끝 미주, 기존 빈 terminal paragraph 새 페이지 경계, 내용
스냅샷 유지, 직렬 COM 재열림, 파일 역할/개정판 분리, 검토된 서식·레이아웃 교정.
재사용 불가: 기존 잘못된 OCR/VERIFIED 표식, 부분 범위의 전체 완료 주장, 미주 heading
위치만으로 만든 경계 PASS, 원문 대조 없이 개수/ZIP/폰트만 확인한 최종 판정.

사용자가 v12 외관/사용 수준을 수용한 사실은 유지한다. 이번 작업은 지시서·코드
보강이며 v12 파일을 다시 저장하거나 COM/전수 원문 검수를 수행하지 않는다.
새 boundary v2 증거가 아직 없는 기존 v1 report를 자동 변환해 PASS하지 않는다.

## 5. 구현 범위와 남는 운영 책임

이번 변경으로 기본 진입 안내·요구 추적·머신 정책·경계 검사 및 기존 출고 함수의
경계 증거 재검사가 저장소에 연결된다. 실제 PDF→OCR→writer 조합은 여럿이며,
새 자료에서 선택한 adapter가 모든 요구를 준수하는지 S0–S2에서 여전히 확인해야 한다.
이를 숨기고 범용 완전 자동 변환이 이미 완성됐다고 말하지 않는다.

특히 source 전수 대조, mixed-layout, 별도 문서 복사/여러 문항 이동, 원문 그림
정확성은 단위 테스트로 대체할 수 없다. 새 오류가 발견되면 V12 ID에 원인·회귀·
실제 경로·교정 영향 범위를 덧붙이고 같은 실패를 다음 교재에서 반복하지 않는다.
