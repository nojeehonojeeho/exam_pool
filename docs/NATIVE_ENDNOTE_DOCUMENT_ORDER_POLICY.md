# 네이티브 미주 문서 순서·문서 분리 정책

이 문서는 PDF→HWP/HWPX 작업에서 문제 본문, 해설, 네이티브 미주를 재사용할 때의
공통 계약이다. 공통 실행 원칙은
[사용자 의도 기반 실행 기본값](USER_INTENT_EXECUTION_DEFAULT.md)을 적용하며,
세부 출고 게이트는 [원문 충실도 v2 작업지시서](PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md)
및 그 문서의 12.20을 함께 적용한다.

## 1. 문서 역할을 먼저 분리한다

원본과 중간 산출물은 다음 세 문서를 각각 독립 파일로 보존한다. 하나의 파일을
복사해 이름만 바꾼 뒤 역할을 선언하는 것으로는 분리된 것으로 보지 않는다.

| 문서 | 허용 내용 | 금지 내용 |
|---|---|---|
| 문제 문서 (`question`) | 원본 읽기 순서의 문제 페이지·문항·보기·선지·문항 자료 | 정답, 풀이, 해설 제목/본문/그림, 해설 미주 body |
| 해설 문서 (`solution`) | 문항 ID 순서의 정답·풀이·해설과 그 편집 가능한 수식·표·그림 | 문제 페이지의 재복제, 문제 본문을 미주 표식으로 가장하는 텍스트 |
| 미주 문서 (`endnote`) | 문항 ID별 정답·해설 body 원장과 native endnote 매핑 | 문제 페이지를 body로 넣기, 다른 문항 body의 혼입·중복 |

세 문서의 stable item ID와 순서 매핑을 manifest로 함께 보존한다. 최종 통합본은
이 세 문서에서 파생되는 별도 산출물이며, 세 원본 문서를 덮어쓰거나 대체하지
않는다. 문제-only 요청에는 해설·미주 문서를 새로 만들지 않는다.

## 2. 통합본의 물리적 순서 계약

통합 HWP/HWPX에는 다음 순서를 강제한다.

1. 주 본문에는 모든 문제 페이지를 원본 읽기 순서로 먼저 배치한다. 첫 번째
   native endnote body가 렌더되기 전까지 문제 페이지가 모두 끝나야 한다.
2. 문제 번호마다 실제 native endnote reference를 정확히 하나 연결한다. `※`,
   `[해설]`, 숨은 텍스트, 복사한 해설 문장 등 평문 표식은 연결을 대체할 수 없다.
3. 대응하는 정답·풀이·해설은 native HWP endnote body에만 둔다. 저장 HWPX의
   모든 `hp:endNotePr/hp:placement/@place`는
   `END_OF_DOCUMENT`이어야 하며, 각주 설정인 `footNotePr`를 미주 근거로
   사용하지 않는다.
4. 따라서 저장·재열림·렌더 후 마지막 문제 페이지 다음에는 미주 영역만 이어져야
   한다. 해설 body를 일반 본문 문단으로 문서 끝에 이어 붙이는 방식은 native
   endnote가 아니며 FAIL이다. 문제와 미주 body가 문항별로 교차하거나 페이지·단
   중간에 interleave되어도 FAIL이다.

문항과 미주의 stable item ID, 인쇄 번호, reference occurrence, body hash 및 순서를
manifest에서 1:1로 대조한다. 미주 개수만 맞는 결과, endnote XML이 존재하기만
하는 결과, 재열림·렌더를 하지 않은 XML-only 결과는 출고 PASS가 아니다.

## 3. 복사·이동 시 링크 보존

출고 전 원본을 보존한 검사용 HWP/HWPX 사본에서 실제 한글 편집 동작을 확인한다.

- 문항 하나를 복사하면 native reference와 그 문항의 linked endnote body가 정확히
  한 세트 증가해야 한다. 복사된 body의 item ID/본문 hash/수식 순서가 선택 문항과
  일치해야 하며, 평문 표식이 복사된 것만으로는 통과시키지 않는다.
- 문항 하나를 이동하면 reference, linked body, 자동번호, body 수식의 multiset이
  보존되어야 한다. reference가 다른 문항 body를 가리키거나 body가 고아가 되면
  FAIL이다.
- 두 시험 모두 저장 후 HWP/HWPX를 재열고, `END_OF_DOCUMENT` placement와 원본
  파일 hash를 다시 확인한다. 한 문항을 복사했다고 문서 전체 수식 수가 두 배가
  되어야 한다고 가정하지 않는다.

COM/재열림 증거가 없는 구조 검사는 이 동작 계약을 증명하지 못한다. 복사·이동
시험은 [네이티브 미주 작업 지시서](PDF_HWP_MATH_ENDNOTE_WORK_RULES.md)의
검수 단계와 `tools/hwp_native_endnote_transfer_probe.py`를 따른다.

## 4. inline solution leakage 차단

문제 문서와 통합본의 주 본문에는 다음이 0건이어야 한다.

- `정답`, `해설`, `풀이` 제목 또는 해당 solution body의 문장·수식·표·그림
- 해설 전용 이미지나 페이지 캡처
- 미주를 흉내 내는 일반 텍스트, 숨은 텍스트, 임의 anchor 문장

검사는 문자열 검색만으로 끝내지 않고, 주 본문 top-level 문단과 native endnote
subList를 별도로 순회한다. 문제 body와 solution body를 문항별로 교차 배치하거나
해설을 본문에 넣어 미주 수를 맞추는 우회는 즉시 FAIL이며, 누출을 제거한 뒤
동일한 source/manifest hash로 재검수한다.

## 5. 원인·발견·증거 회계

진행률과 출고 판정에서 다음 수를 서로 대체하지 않는다.

| 필드 | 의미 | 집계 규칙 |
|---|---|---|
| `raw_finding_count` | 실행 원장에 기록된 독립 finding 수 | 진단 grouping을 해도 원장을 삭제·deduplicate하지 않고 그대로 센다 |
| `unique_root_cause_candidate_count` | raw finding을 묶은 진단 후보 수 | 후보일 뿐이며 기본 `candidate_only=true`, `resolved=false`; 원인 수 감소만으로 PASS하지 않는다 |
| `evidence_closed_item_count` | 필수 source evidence가 모두 있고 `evidence_status=CLOSED`인 고유 문항 수 | `VERIFIED` 라벨, 출력 파일 존재, endnote 개수만으로 닫지 않는다 |
| `evidence_open_item_count` | authoritative scope에서 아직 닫히지 않은 고유 문항 수 | 매 실행 `scope_item_count - evidence_closed_item_count`로 산출하며 과거의 고정 숫자를 재사용하지 않는다 |
| `release_blocker_count` | 출고를 막는 raw finding 및 기타 차단 수 | root-cause grouping으로 줄이지 않으며 독립 release gate가 직접 확인한다 |

한 root cause에서 여러 raw finding이 나와도 raw finding과 release blocker는 각각
그 수를 유지한다. 반대로 같은 문항의 서로 다른 수식·표·그림 evidence 문제를
하나의 원인으로 합치지 않는다. `evidence_open_item_count=0`이어도 raw finding,
blocking item, release blocker 또는 문제 본문 누출이 남아 있으면 `FINAL_PASS`가
아니다. 자세한 합성 회귀는
`PDF_HWP_SOURCE_FIDELITY_V2_REGRESSION_SPEC.md`의 root-cause 회귀와
`tests/test_v2_root_cause_grouping.py`, `tests/test_v2_execution_report.py`를
정본으로 사용한다.

## 6. 최소 출고 체크리스트

- [ ] 문제·해설·미주 문서가 별도 파일이고 stable item ID 매핑이 닫혔다.
- [ ] 통합본의 모든 문제 페이지가 먼저 나오고, 미주 body는 문서 끝에만 렌더된다.
- [ ] 모든 문제에 실제 native reference가 1개씩 연결되고 body 순서가 일치한다.
- [ ] 주 본문에 inline solution leakage가 없고 평문 미주 표식이 없다.
- [ ] 검사용 사본의 복사·이동에서 linked endnote가 보존된다.
- [ ] raw finding, root-cause candidate, evidence-open, release blocker를 별도 보고했다.
- [ ] 구조 검사·HWP/HWPX 재열림·복사/이동·렌더 증거가 모두 같은 source/manifest
  hash에 연결되어 있다.
