# PDF → HWP/HWPX 출고 상태·FINAL 승격 작업지시서

공통 실행 기본값은 [사용자 의도 기반 실행 기본값](USER_INTENT_EXECUTION_DEFAULT.md)을
적용한다. 출고 요청은 가능한 검증을 끝까지 수행하되, 미검증 상태를 FINAL로 승격하지 않는다.

현재 단일 실행의 추가 계약은
[HIGH-END 실행 계약](HIGHEND_4SUBJECT_ASTRA_LOW_FINAL_EXECUTION_20260908.md)에 있다.
정책 설정·정책 테스트·커밋 성공은 실제 문서의 출고 증거를 대신하지 않는다.

문서 버전: 1.2 · 2026-09-13

## 목적

파일이 생성되거나 XML 구조 검사를 통과했다는 이유만으로 최종본으로 표시하지
않는다. 모든 PDF→편집형 HWP/HWPX→네이티브 미주 산출물은 `CANDIDATE`로 시작하고,
내용·수식·미주·서식·전 페이지 시각 증거가 닫힌 경우에만 `FINAL`로 승격한다.

## 상태 순서

`GENERATED → REOPEN_PASS → CONTENT_PASS → EQUATION_PASS → ENDNOTE_PASS → STYLE_PASS → VISUAL_PASS → FINAL`

검사 증거가 없거나 일부 범위만 검사된 경우 상태를 건너뛰지 않는다. 실패·미확정은
`FAIL`, `BLOCKED`, `NEEDS_REVIEW`로 남긴다.

## 후보와 최종 산출물

- 후보: `outputs/candidate/` 및 `document-release-status.json`의 `final=false`
- 최종: `outputs/final/` 및 모든 게이트 `true`, `findings=[]`, `final=true`
- 기존 파일명에 `FINAL`·`완성본`이 들어 있어도 상태 JSON이 우선한다.
- 기존 원본·산출물을 삭제하거나 덮어쓰지 않는다.

## FINAL 필수 게이트

1. HWP/HWPX 저장·닫기·재열림 성공, 복구 알림·손상·잠금 파일 0건
2. 문제·해설 문장, 숫자·부호·정답·문항 ID·순서·표·그림·수식 스크립트·미주 본문 불변
3. 모든 수식의 네이티브 편집성, 스크립트·소유권·순서·글꼴·크기·기준선 및 600/900dpi 원문 대조
4. 통합본 주 본문에 모든 문제가 원문 검수 `source reading order`로 정확히 한 번씩만
   있고, 각 문항에 native endnote reference가 정확히 하나 연결되며, 정답·풀이·해설
   body는 해당 native endnote 안에만 존재하고 `END_OF_DOCUMENT`에 렌더됨을 확인한다.
   본문과 solution body의 문항별 교차 배치, 미주 누락·중복·오연결은 FAIL이다.
   복사 시 대응 미주 reference/body가 정확히 한 세트 추가되고 이동 시 reference,
   body, 자동번호·수식이 보존되는 검사용 사본 증거도 필수다.
5. 페이지·단·글자·문단·표·그림·간격·고아 문단 서식 검사
6. 모든 페이지를 300dpi 이상 렌더하여 잘림·겹침·경계 침범·순서·공백을 검사
7. 상태 JSON과 코드·원본·원장·출력 해시가 연결되고, findings가 빈 배열

구조 개수·XML 파싱·태그 개수·파일 생성만 통과한 상태는 의미 PASS가 아니다.
플레이스홀더, 미검수 OCR, 설명문만 있는 그림, 평문/이미지 수식 대체, 가짜 미주는
자동 FAIL한다. 대표 페이지 검사는 전 페이지 검사를 대체하지 못한다.

## HIGH-END 4과목 독립 출고 게이트

v6 후보 요약의 `status=PASS`, 구조 감사 PASS, 미주 수 `76+50+60+106=292`,
또는 COM `12/12`만으로 `FINAL`을 부여하지 않는다. 이 숫자들은 후보 패키지의
관찰값일 수 있으며 전체 원본의 문항·수식·기하 대조가 끝났다는 뜻이 아니다.
출고 직전에 저장소의 재사용 가능한 독립 게이트를 실행한다.

```text
python tools/highend_delivery_gate.py <delivery-summary.json> `
  --scope-root <directory-containing-math_up-math_down-math2-probability> `
  --com-report <com-dispatchex-report.json> `
  --json <audit-report.json>
```

이 명령은 입력 요약·범위 manifest·COM report를 읽기만 하며 HWP/HWPX/PDF/COM
파일과 registry를 변경하지 않는다. `--json`을 생략하면 보고서를 표준 출력으로
내보낸다. 독립 판단의 `promotion_allowed=true`일 때만 종료 코드 0이며,
그 외에는 `BLOCKED`와 차단 finding을 남긴다. 요약에 기록된 `final=true`나
최상위 `PASS`는 독립 게이트의 근거로 사용하지 않는다.

독립 게이트는 다음을 모두 요구한다.

1. 정확히 `고등수학상`, `고등수학하`, `수학II`, `확률과_통계` 네 과목의 scope
   manifest가 각각 존재한다.
2. 각 manifest가 authoritative full-source denominator, 명시적 full-source
   closed 상태(`FULL_SOURCE_CLOSED`, `FULL_SOURCE_VERIFIED`,
   `SOURCE_FIDELITY_CLOSED`, `SOURCE_FIDELITY_VERIFIED` 중 하나),
   `strict_pass=true`, human-review 미해결 없음, 문제·해설 원본
   PDF의 SHA-256·쪽수 증거를 갖는다. 각 항목은 원본 PDF SHA-256, page, bbox,
   crop SHA-256, review ID를 갖춘 `evidence_status=CLOSED`여야 하며, 이 조건이
   없는 `items` 배열·`VERIFIED` 숫자·선택 범위 숫자는 폐쇄 수로 세지 않는다.
   authoritative denominator가 0보다 크면 item-level records 배열이 반드시
   존재하고 denominator와 길이가 같아야 한다. generic `CLOSED` status나
   aggregate closed count만으로는 full-source closure를 주장할 수 없다.
3. 통합 미주 수는 네 manifest의 닫힌 full-source denominator와 항목별로
   일치해야 한다. 후보 package의 `endnotes == autonum`이나 `106/106` 같은
   수치 일치는 source closure를 대신하지 않는다. denominator가 없거나
   `strict_pass=false`, `REVIEW_REQUIRED`, `OPEN`이면 반드시 차단한다.
4. COM report는 정확히 12행(과목별 3 role)이고, 각 행에 register/open/save,
   write/reopen readback, dispatch event, 소유 PID 종료, 승인창 열거 결과,
   전후 입력 SHA-256 안정성이 있어야 한다. HWP/HWPX 출력 SHA-256은 summary의
   해당 package 파일과 교차 연결되어야 하며 COM report의 `PASS` 주장만으로
   통과시키지 않는다.

5. 출고 요약의 `files`는 생략할 수 없다. 비어 있지 않은 배열의 모든 항목에
   `subject`, `name`, 64자리 `sha256`가 있어야 하며, 네 과목마다 `문제`,
   `정답및풀이`, `미주작업_완료`의 HWP·HWPX 쌍(총 24개)이 정확히 한 번씩
   기록되어야 한다. 파일 목록이 없거나 비어 있으면 COM 해시 연결을 검증할
   수 없으므로 즉시 차단한다. 동일 `(subject, name)` 중복도 차단한다.

6. COM 12행은 과목별로 서로 다른 세 role을 명시해야 한다. 새 report는 각
   행에 `role`을 기록하고, 레거시 report는 HWP/HWPX 출력 파일명에서 role을
   모호하지 않게 추론한다. 과목별 role 집합이 정확히
   `{문제, 정답및풀이, 미주작업_완료}`가 아니면 `COM_ROLE_SET_INVALID`로
   차단한다. subject만 3행 반복한 report는 세 문서의 재열림을 증명하지
   못한다.

판정 보고서에는 `source_scope_closed`, `endnote_counts_reconciled`,
`com_provenance_closed` 게이트와 과목별 `declared_item_count`,
`evidence_closed_item_count`, `evidence_open_item_count`를 보존한다. 범위가
부분적이면 후보로 계속 기록하고, source fidelity가 닫힌 새 manifest와 재열림
증거를 확보한 뒤 같은 명령을 다시 실행한다. 실제 출력물을 FINAL 위치로
복사하거나 파일명만 바꾸는 행위는 이 독립 판정을 우회하지 못한다.

파이프라인 경계에서는 반드시 `app.pdf_hwp_pipeline_gate.require_final_release`를
호출한다. 단계 체인이 PASS여도 이 호출의 반환값 `final=true`가 아니면 패키징·공개를
진행하지 않는다. 이 경계는 실제 evidence root, 존재하는 evidence 파일, 일치하는
SHA-256, layout contract와 모든 차단 finding을 함께 확인하며, 누락된 호출 자체를
회귀 결함으로 취급한다.

## 범위·재구성·증거 종료를 분리한다

문항 인벤토리에 잡힌 수는 제작 완료나 원본 대조 완료를 의미하지 않는다. 상태
보고서에는 다음을 별도로 기록한다.

```text
scope_item_count                 = 원본에서 작업 대상으로 선언한 문항 수
inventory_item_count             = 문항 인벤토리에 발견된 수
reconstructed_item_count         = SourceItemIR로 재구성된 수
evidence_closed_item_count       = 원본·출력·재열림 증거가 모두 닫힌 수
evidence_open_item_count         = 아직 하나라도 열린 수
raw_finding_count                = 하위 검사 결과의 총 건수
root_cause_count                 = root_cause_id로 묶은 독립 원인 수
```

`raw_finding_count`를 실제 오타·누락 개수로 보고하지 않는다. 같은 원인에서
파생된 bbox 미확인, MathIR 미확인, writer 미확인 등의 하위 결과는 하나의
`root_cause_id`로 묶어 우선순위를 정하고, 원시 원장은 삭제하지 않는다. 상위
원인을 수정한 뒤 strict validator를 다시 실행하여 raw finding과 root cause를
각각 재집계한다. 기존에 evidence가 닫힌 문항은 source/hash/compiler/writer
입력이 유지되는 경우에만 체크포인트로 재사용하며, 입력이 바뀌면 다시 연다.

문항을 재구성했지만 증거가 열려 있는 상태는 `RECONSTRUCTED` 또는
`EVIDENCE_OPEN`으로 기록한다. `22/106` 같은 표기는 제작 문항 수가 아니라
증거 종료 문항 수로만 사용하며, `106/106` source verified와 모든 게이트가
닫힌 뒤에만 출고 판정을 검토한다.

## 자동화 세션과 중단 규칙

기존 HWP/COM 세션이 살아 있으면 새 COM 작업을 병렬로 시작하지 않는다. CPU·메모리
상태, PID, 작업 경로, 마지막 산출물 수정 시각을 `execution-state.json`에 남기고,
현재 작업 직속 보조 프로세스가 고착되었다는 객관적 증거가 없는 한 강제 종료하지
않는다. 저장·닫기·재열림에 실패한 세션은 무한 재시도하지 않고 체크포인트와
`BLOCKED` 상태로 넘긴다. 재개 시에는 마지막 성공 게이트부터 직렬로 수행한다.

## 후보 산출물의 정직한 보고

생성 파일, HWPX XML 정상, equation 개수 일치, 300dpi 자동 렌더가 모두 성공해도
원본 수식 crop·MathIR·문항별 의미 비교·미주 item mapping·전 페이지 수동 시각
비교가 닫히지 않았다면 `CANDIDATE` 또는 `BLOCKED`다. 원본과 다른 페이지 크기·단
구성·페이지 수가 발견되면, 사전에 선언한 `effective_layout_contract`와 비교해
계약을 위반한 경우에만 `PAGE_GEOMETRY_MISMATCH`를 차단 finding으로 남긴다. 문제
범위만 추출하거나 해설을 미주로 재배치한 경우 전체 원본 쪽수와 출력 쪽수의
불일치만으로 차단하지 않는다. source-region 모드에서는 원문 페이지·영역의 실제
기하를, item-reflow 모드에서는 선언한 편집 프로필과 문항/개체 순서를 검사한다.
`FINAL` 디렉터리로 복사하거나 파일명에 `완성본`을 붙이는 후처리는 허용하지 않는다.

## 상태 증거 파일

모든 산출물 묶음에는 `document-release-status.json`을 둔다. 최소 필드는
`document`, `source_document`, `status`, `profile`, `generated`,
`reopen_pass`, `content_pass`, `equation_pass`, `endnote_pass`, `style_pass`,
`visual_pass`, `final`, 각 SHA-256, 문항·수식·미주 개수, `findings`,
`evidence_files`, `checked_at`, `code_commit_sha`이다.

`final`은 사람이 파일명을 바꾸어도 자동으로 `true`가 될 수 없다. 다음 조건을
프로그램으로 모두 확인한다.

```text
reopen_pass && content_pass && equation_pass && endnote_pass
&& style_pass && visual_pass && findings.length == 0
&& hwp_sha256, hwpx_sha256가 각각 64자리 SHA-256
&& evidence_root가 존재하고 evidence_files가 실제 파일·SHA-256과 일치
&& effective_layout_contract가 source/role/scope와 일치
```

`evidence_files`의 경로·해시 문자열만으로는 증거가 아니다. 게이트가 실행 시
실제 파일을 읽고 SHA-256·run_id·scope_hash를 재확인한다. `pages=[]`, 중복/누락
페이지, 미주 번호·fingerprint 누락, source manifest schema 실패, authoring
`match_method`만 있는 수식은 모두 차단한다. 정상 관찰 기록은 미해결 finding과
분리하며, 경로명에 `pending`이 포함되었다는 이유만으로 본문 placeholder로
판정하지 않는다.

## 현재 진행 중인 산출물 처리

진행 중인 HWP 자동화 세션은 강제 종료하지 않는다. 생성된 문제·해설 파일과
생성 중인 미주 파일은 모두 `CANDIDATE`로 기록한다. 세션이 끝난 뒤에도 재열림,
내용 불변, 수식 구조, 문항별 미주 연결, 스타일, 전 페이지 시각 검사를 처음부터
실행한다. 모든 게이트가 닫히기 전에는 FINAL·완성본·전체 PASS·출고 가능으로 보고하지
않는다.

## 범위 집계 보정 규칙

출고 게이트는 `candidate_id_count`, `declared_item_count`,
`legacy_reviewed_scope_count`, `evidence_closed_item_count`,
`evidence_open_item_count`를 분리해 기록한다. `review_status=VERIFIED`인 과거
원장 수는 레거시 검토 수일 뿐이다. 문항별 원본 PDF·페이지·bbox·crop SHA-256·검수
실행 ID·문제-해설 대응이 명시되고 `evidence_status=CLOSED`인 항목만 증거 종료 수에
포함한다. 후보 ID와 선언 항목 수의 차이는 변형문항·소문항·하위 블록 산식으로
기록하며 실제 누락 수로 자동 승격하지 않는다.

Step B처럼 기본문항과 `-1` 변형문항이 같은 인쇄 번호 아래 있는 경우에는 원본에서
확인된 두 항목을 별도 ID·bbox·해설 대응으로 확장한다. 번호 목록 길이나 HWP 개수만으로
출고 범위를 확정하지 않는다.

## COM 재열림 종료 조건

COM 실행은 직렬 잠금 아래에서 `run_id`, 소유 PID, 재열림 PID, 단계별 deadline을
기록한다. 승인창 조회 실패는 승인창 0회가 아니라
`WINDOW_ENUMERATION_UNAVAILABLE`로 처리한다. 저장·닫기·재열림·PDF 출력과 모든
작업 소유 PID 종료가 확인된 경우에만 `reopen_pass=true`를 부여하며, XML-only 또는
`skip-com` 결과는 COM PASS로 승격하지 않는다.

## 문항 블록·긴 수식·경계 렌더링 보강 계약

표 셀 안에 문항이 들어 있는 문서에서는 `pageBreak`만 추가해도 한글이 문항의
마지막 선택지나 수식을 다음 페이지로 고아 배치할 수 있다. 따라서 문항 제목·조건·
보기·선지·관련 그림·독립 수식을 하나의 source block으로 식별하고, 같은 블록의
마지막 문단을 제외한 문단에 native `keepWithNext=1`을 적용한다. 중첩 표와
`subList` 안의 문단도 문서 읽기 순서로 포함하며, 각 복제 `paraPr`에는 새 ID를
부여하고 `paraProperties/@itemCnt`를 갱신한다. 이 보정은 텍스트·수식·표 셀·그림·
미주 anchor를 변경하지 않아야 하며, 저장 전후의 문단·개체 fingerprint가 같아야
한다. `keepWithNext` 적용 전후 영향 페이지는 COM 재열림과 300dpi 렌더에서 다시
검사한다.

긴 native 수식은 글자 축소·이미지 대체·항 삭제로 해결하지 않는다. 원본 occurrence
하나와 MathIR를 유지한 채 최상위 등식/항 경계에서만 HWP `#` 줄바꿈 또는
`eqalign`을 삽입할 수 있다. `<=`, `>=`, `!=`, 음수 부호와 괄호 내부 등호는 줄
바꿈 경계로 사용하지 않는다. 변환 전후 토큰 수·순서·source hash를 비교하고,
저장 HWPX와 COM 재열림에서 equation count·script·baseUnit을 다시 대조한다.
수식 줄바꿈 결과는 영향 페이지의 실제 렌더에서 오른쪽 잘림·겹침·문장부호 고립이
없어야 하며, 하나라도 남으면 `VISUAL_EQUATION_WRAP_FAIL`로 차단한다.

경계 렌더 QA에서 중앙 단 구분선·페이지 프레임처럼 문서 내용이 아닌 선이 안전
경계를 침범하는 경우에는 원본 캡처와 좌표를 근거로 한 명시적 `ignore_mask`만
허용한다. 마스크는 보고서에 경로·크기·SHA-256·사유·적용 페이지를 기록하고,
마스크 적용 전 raw 결과와 적용 후 결과를 모두 보존한다. 마스크로 문자·표·수식의
실제 spill을 숨길 수 없으며, 내용 잉크가 경계를 넘으면 계속 FAIL이다. 정상적인
경계 마스크를 적용한 뒤에도 모든 페이지가 PASS이고, 전 페이지 시각검토가 끝나야
`visual_pass=true`로 기록한다.
