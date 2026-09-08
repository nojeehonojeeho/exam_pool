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
구성·페이지 수가 발견되면 `PAGE_GEOMETRY_MISMATCH`를 차단 finding으로 남긴다.
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
&& hwp_sha256 != "" && hwpx_sha256 != ""
```

## 현재 진행 중인 산출물 처리

진행 중인 HWP 자동화 세션은 강제 종료하지 않는다. 생성된 문제·해설 파일과
생성 중인 미주 파일은 모두 `CANDIDATE`로 기록한다. 세션이 끝난 뒤에도 재열림,
내용 불변, 수식 구조, 문항별 미주 연결, 스타일, 전 페이지 시각 검사를 처음부터
실행한다. 모든 게이트가 닫히기 전에는 FINAL·완성본·전체 PASS·출고 가능으로 보고하지
않는다.
