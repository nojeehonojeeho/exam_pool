# 교사 native HWP 재사용 요구·실패 추적

확인한 요구 목록이지 대화 전체의 기억이나 누락0의 증명이 아니다.
PDF/OCR45개는 [V12-01~45](PDF_HWP_V12_FEEDBACK_TRACEABILITY.md)를 승계한다.
추가28개는 아래와 같다. 실제 교재/개인 경로·근거는 로컬 manifest에만 둔다.

| ID | 실패 → 결정 | 코드·검사 | 범위 |
|---|---|---|---|
| TW01 | 견본/합병 혼동 → 모드 명시 | build.mode | append 별도 adapter |
| TW02 | 표지수=문항수 → ID/역할 | build bijection | 합성2/4/7개 |
| TW03 | 변형·반복·공통과목 제외 → 동일집합 | candidate_item_ids | 원장 대조 별도 |
| TW04 | 가짜 선지/풀이 → 창작 금지 | native payload | OCR 추측 폐기 |
| TW05 | OCR 행=문단 → native 기본 | native_staged_reflow | raw adapter 먼저 |
| TW06 | v3 glob/고정 경로 → 명시 config/hash | bound / CLI | 덮어쓰기 거부 |
| TW07 | notes 미정의 → 지역 runtime 목록 | build 실행 회귀 | old builder 폐기 |
| TW08 | refList/ID 충돌 → 의미 해시 | Package.resolved | import 별도 검증 |
| TW09 | border 전체 변경 → page만 변경 | remove_page_frame | 표/조건/가운데선 보존 |
| TW10 | font 이름만 동일 → 역할/언어/렌더 | profile/font gate | XML만 PASS 금지 |
| TW11 | 띄어쓰기/분절 → 공백도 검사 | payload text | 공백 부정 테스트 |
| TW12 | 보기 나열 → 3+2 탭/기하 | profile/render | 긴 보기 예외 |
| TW13 | 필기공간 없음 → 마지막 개체부터 실측 | workspace evidence | 빈엔터/캐시 불충분 |
| TW14 | 사각틀 → B42단/가운데선 | resolved border/B4 | 원래 표 선 별도 |
| TW15 | 타과목 머리말 → source asset | header binding/render | crop 승계 금지 |
| TW16 | 제목만 빈쪽 → 중복 break 금지 | representative render | 경계별 시험 |
| TW17 | 같은 paraPr의 본문 제거 → 내용 분류 | heading hash/test | 실제 결함 수정 |
| TW18 | header 중복 → control 한 번 | header regression | Open 실패 후 수정 |
| TW19 | 다음 단원표 미주 혼입 → 경계 교정 | leaked_section_metadata | source-bound exclusions |
| TW20 | 정답/그림 다른 단 → 실제 배치 확인 | render exception | OPEN: 속성만으론 불충분 |
| TW21 | 수식 과축소/변형 → script 불변 | equation payload | 가독성 예외 필요 |
| TW22 | 그림수/namespace 오검사 → hc:img SHA | payload/image test | 셀/그림 순서 검사 |
| TW23 | 중간 해설 → 전체 문제 뒤 native | placement/boundary | 바로 다음 물리쪽 |
| TW24 | anchor만copy → 문항 전체copy/move | COM/payload | 대표5개 역순·이동 |
| TW25 | COM 고착 → lease/deadline/소유 | supervisor/security | timeout 보존 |
| TW26 | 빈checks/고정수치 PASS → required schema | release_gate/test | stale hash도 차단 |
| TW27 | 72dpi=전수 사람검수 → 증거 분리 | render/manual ledger | 본 쪽만 명시 |
| TW28 | dirty 무차별commit/교재공개 → 분리 | worktree/snapshot | exact staging |

## SUPERSEDED

기준본 항상 형식만/항상 합병, OCR 행=문단, 숫자ID=의미, 공유border 일괄
치환, 개수/ZIP만 FINAL, marker 수량 확정, 다음 제목까지 해설 포함,
anchor만copy, 제목쪽-1 역산, 고정수치·예외횟수 PASS, 무한 COM 재시도.

## 미확인·후속 검증

새 출판사/다구역/복합문항 raw adapter, append 실제 재현, 모든 역할의 자동
폰트/그림·수식 가독성 전수 증거, 첫 그림 해설 표제의 단 분리 일반해법,
이번에 열람하지 않은 과거 대화/첨부 개별 요구. 기존45+추가28 밖의 요구는
새 ID와 구현·검사를 연결한다.
