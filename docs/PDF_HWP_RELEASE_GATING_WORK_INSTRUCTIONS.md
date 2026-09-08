# PDF → HWP/HWPX 출고 상태·FINAL 승격 작업지시서

문서 버전: 1.0 · 2026-09-08

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
4. `문항 → 미주 참조 → 미주 번호 → 대응 해설` 전수 일치
5. 페이지·단·글자·문단·표·그림·간격·고아 문단 서식 검사
6. 모든 페이지를 300dpi 이상 렌더하여 잘림·겹침·경계 침범·순서·공백을 검사
7. 상태 JSON과 코드·원본·원장·출력 해시가 연결되고, findings가 빈 배열

구조 개수·XML 파싱·태그 개수·파일 생성만 통과한 상태는 의미 PASS가 아니다.
플레이스홀더, 미검수 OCR, 설명문만 있는 그림, 평문/이미지 수식 대체, 가짜 미주는
자동 FAIL한다. 대표 페이지 검사는 전 페이지 검사를 대체하지 못한다.

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
