# 수학 HWP/HWPX 기준 서식 작업지시서

공통 실행 기본값은 [사용자 의도 기반 실행 기본값](USER_INTENT_EXECUTION_DEFAULT.md)을
적용한다. 서식 보정 요청은 안전한 범위에서 실제 적용과 검증까지 진행한다.

원문 배치 선택·실제 편집성·최종 승격은
[원문 충실도 v2](PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md)를 우선 적용한다.
v2 문서 반영과 코드 구현 완료를 구분한다. 아래 기본 프로필의 측정 상태는 해당
기준 문서에 대한 사실이며, 모든 새 PDF가 같은 규격/글꼴이라는 뜻이 아니다.

이 문서는 저작권 있는 시험 자료를 포함하지 않는 범용 작업 규칙이다. 목적은
수학 문제·해설을 편집 가능한 HWP/HWPX로 재조판할 때 기준 서식을 먼저
확정하고, 서식 적용이 내용·문항 연결을 훼손하지 않았음을 자동으로 증명하는
것이다. 실제 기준 문서에서 측정하지 않은 값은 임의로 확정하지 않는다.

## 작업 순서와 승격 조건

1. 기준 HWP/HWPX를 내용 인벤토리로 읽는다. 문항 ID, 네이티브 미주, 수식
   script, 표 셀 텍스트, 그림의 실제 BinData SHA-256을 수집한다.
2. 기준 문서의 Page/Column/Char/Para/Table/Figure/Endnote 속성을 측정해
   `config/math_hwp_reference_style_v1.json`의 `styles`에 기록한다. 아직 측정하지
   않은 새 프로필은 측정 전까지 `measured: false`,
   `reference_measurement_status: "pending"`, `reference_source: null` 상태를
   유지한다. 현재 저장소의 v1 프로필은 기준 자료의 측정·검수가 끝난
   `measured: true`, `reference_measurement_status: "verified"` 상태이다.
3. `app.hwp_reference_style.preflight_reference_style()`를 실행한다. 프로필
   schema, 7개 서식군, provenance, 프로필 SHA-256, 기하 허용오차(최대 0.5 mm)를
   모두 통과한 경우에만 문서 builder를 실행한다. 미측정 프로필은 분석에는
   사용할 수 있지만 제작 산출물을 PASS로 승격할 수 없다.
4. 한 문서의 staging 사본에 `apply_reference_style()`를 적용한다. 어댑터는
   표시 속성만 변경하고, 적용 보고서에 `profile_sha256`, `passed: true`,
   `applied: true`를 남겨야 한다.
5. style QA 통과는 서식 체크포인트로만 기록한다. 원문 충실도·내용 보존·실제 편집성·
   요청된 미주·출고 해시 검증까지 통과해야 최종 폴더로 승격한다. 실패한 staging과
   원인 보고서는 보존하되 최종본으로 표시하지 않는다.

서식 적용은 수식 script, 문항 ID, 미주 연결 또는 그림 파일을 고치기 위한
단계가 아니다. 내용 해시가 하나라도 변하면 즉시 FAIL이다.

수식 변환의 입력은 [PDF_HWP_MATH_FORMULA_SOURCE_REVIEW.md](PDF_HWP_MATH_FORMULA_SOURCE_REVIEW.md)의
`math-source-manifest-v1` 검수 원장으로 제한한다. 600 dpi(불명확한 영역은 900 dpi)
확대, PDF crop SHA-256, 문항·좌표·순번, MathIR, `operator_bounds_mode`와
`review_status: VERIFIED`가 없는 수식은 writer에 전달하지 않는다. OCR 문장만으로
작성된 manifest, 수식 수가 0인 미검수 스캔 페이지, 상·하한을 추측한 식은 자동 FAIL이다.

## 서식 프로필 계약

프로필은 `schema_version: "math-hwp-reference-style-v1"`을 사용한다. 다음
7개 키가 반드시 있어야 한다.

`page`, `column`, `char`, `para`, `table`, `figure`, `endnote`

### 긴 수식의 단 배치 예외

이 절은 기본 편집 프로필을 선택한 `item_reflow`에만 적용한다.
`source_region_layout`에서는 페이지별 원문 규격과 단을 사용하며 B4/1단 변형으로
자동 대체하지 않는다. 두 요구가 충돌하면 배치 실현 가능성과 차이를 보고한다.

기본 편집 프로필은 기준 HWP에서 측정한 B4 2단(단 간격 8 mm)이다. 다만 원문 수식
script를 변경하지 않은 네이티브 수식의 폭이 안전 단 폭 104.5 mm를 넘고,
자동 줄바꿈으로 보존할 수 없는 장문 논술형 문서는 기준 HWP에 실제 존재하는
B4 1단 변형을 해당 구역에 적용한다. 이 예외는 글자·수식 축소나 잘림을
허용하는 규칙이 아니다. 적용 보고서에
`reference_long_formula_single_column`을 기록하고, 300 dpi 전 페이지 렌더링에서
잘림 0건과 과대 공백 0건을 확인해야 한다. 수식 script, baseUnit 1100,
HYhwpEQ, 미주 참조와 본문은 그대로 유지한다.

수치 단위는 geometry가 mm, typography가 pt이다. 기하 차이는 ±0.5 mm 이내,
글꼴·크기·행간·문단 간격은 기준값과 정확히 일치해야 한다. 밀도는 페이지별
값의 min/median/max를 기록하며 프로필의 `density` 범위를 벗어나면 FAIL이다.

측정 근거가 부분적으로만 있을 때는 `reference_measurement_status: "partial"`과
검증·미확정 필드 목록을 남기고 `measured: false`를 유지한다. 근거가 없는
경로를 추측해 넣지 않으며, `measured: true`는 기준 자료의 필수 서식군을
실제로 측정하고 검수한 뒤에만 설정한다.
프로필의 canonical JSON hash(`profile_sha256`)는 공백·키 순서와 무관하게
계산하며, 적용 보고서와 QA 보고서에서 동일해야 한다. 내용 해시는 문항 ID의
원본 순서를 포함하므로, 스타일 적용 중 문항·미주 순서를 바꾸어도 PASS할 수
없다.

## 검증된 기본 프로필 v1

`수능완성_수학_문제해설_미주_기본서식_v1`은 문제 본문용 작업전 HWP와
네이티브 미주용 완성본 HWP를 각각 읽기 전용 임시 HWPX로 변환한 뒤 COM 및
HWPX XML을 함께 조사해 확정했다. 원본 파일·문장·수식 script는 저장소에
포함하지 않고 두 기준 파일의 SHA-256만 provenance로 기록한다.

- 내부 용지: B4 257×364 mm(72852×103180 HWPUNIT), 세로
- 여백: 좌우 20 mm, 위 20 mm, 아래 15 mm, 머리말·꼬리말 거리 15 mm
- 본문/미주: 2단, 동일 폭, 단 간격 8 mm, 명시적 단 구분선 없음
- 본문 글자: 함초롬돋움 11 pt, 장평 100%, 자간 0%, 기준선 0%
- 제목: 함초롬돋움 13 pt 굵게; 문항·풀이 제목은 11 pt 굵게
- 본문 문단: 양쪽 정렬, 160% 줄간격, 뒤 2 pt
- 문항 제목: 앞 12 pt, 뒤 3 pt, 다음 문단과 함께, 문단 보호
- 독립 수식 문단: 가운데, 160%, 앞 3 pt, 뒤 7 pt
- 네이티브 수식: HYhwpEQ 11 pt, `baseUnit=1100`, 글자처럼 취급,
  본문과 함께 이동, 겹침 금지
- 표: 0.12 mm 검정 실선, 좌우 셀 여백 1.8 mm, 상하 0.5 mm
- 미주: 아라비아 숫자와 `)` 접미, 연속 번호, 문서 끝 배치,
  0.12 mm 검정 구분선, 선 위 3 mm·아래 2 mm

### 통합본 미주 배치의 실제 사용 계약

통합본은 문제 복사·이동 시 대응 해설이 따라오도록 만드는 문서다. 모든 과목에서
주 본문에는 모든 문제를 원문 검수 `source reading order`로 정확히 한 번씩만 먼저
배치하고, 각 문제번호 뒤에는 실제 native endnote reference를 정확히 하나만
연결한다. 정답·풀이 문단과 해설 제목·본문 및 해설 소속 수식·표·그림은 주 본문에
넣지 않고 대응 native endnote body 안에만 같은 원문 순서로 둔다. 모든 미주는
`END_OF_DOCUMENT`에 렌더되어야 하며, 문제와 solution body를 문항별로 교차 배치하지
않는다. 평문 `[해설]`·`※` 표식이나 해설 페이지를 주 본문 뒤에 단순 병합하는 방식은
native 미주로 인정하지 않는다.

HWPX를 저장한 뒤 모든 `hp:endNotePr/hp:placement/@place`가
`END_OF_DOCUMENT`인지 확인한다. `footNotePr`의 `EACH_COLUMN`은 각주 기본값일
수 있으므로 미주 위치 판정에 사용하지 않는다. 배치 선언 누락·문서 끝 이외의
placement·문항/미주 순서 불일치는 자동 FAIL로 기록한다. 한글 재열림과 300 dpi
렌더에서 마지막 문제 다음에 미주 영역만 이어지는지, 문제 하나를 복사하면 선택
문항의 native endnote reference/body가 정확히 한 세트 추가되는지, 이동하면
reference·body·자동번호·수식이 보존되는지를 저장·재열림 후 확인한 뒤에만 통합본을
출고한다. 이 규칙은
`PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md` 12.20과
`app.endnote_qa_gate.audit_hwpx`의 배치 게이트를 함께 적용한다.

실제 HWP 내부 pagePr는 B4이지만 Hanword PDF 출력기가 A4로 배율 출력할 수
있다. HWP/HWPX 내부 값과 PDF 출력 용지·배율을 각각 기록한다. 원문 배치 비교는
같은 물리 배율로 수행하고 자동 축소를 용지/좌표 일치의 근거로 쓰지 않는다.

사용자가 별도의 기준 HWP를 지정하면 그 문서가 우선한다. 별도 기준이 없을
때만, 그리고 원문 영역 배치 요청이 없는 경우에 이 v1 편집 프로필을 기본으로 적용한다.
원문 배치와 기본 글자 스타일을 조합하면 선택값·측정값·충돌을 분리해 기록한다.
사용자 요청이 특정 글꼴·배치를
명시하면 해당 요청이 프로필보다 우선하되, 내용·수식·미주 QA는 약화하지 않는다.

## 내용 보존 gate

스타일 정의 목록만으로 적용을 판정하지 않는다. 실제 텍스트 run의 유효 charPr/paraPr,
직접 지정과 상속, HWPX switch 분기와 단위, COM readback을 비교한다. 바깥 wrapper의
스타일을 모든 하위 문단의 실제 스타일로 간주하지 않는다. 1×2 바깥 표와 native 2단을
구별하여 배치·복사·미주 이동을 시험한다. 원본 글꼴 미확인은 unknown으로 기록한다.

전후 인벤토리의 다음 hash가 모두 동일해야 한다.

- 문항 ID와 순서
- 네이티브 수식 script와 순서
- 모든 네이티브 표의 셀 텍스트
- 문항 소유 그림 및 문서 전체 그림의 SHA-256
- 위 요소를 합친 content SHA-256

HWPX에서는 `Contents/section*.xml`뿐 아니라 헤더·꼬리말 등 모든 XML member의
`hc:img` 참조와 모든 `BinData/*`를 조사한다. 참조되지 않거나 SHA가 바뀐
리소스는 FAIL이다. HWP 바이너리는 동일 필드를 제공하는 COM/어댑터 인벤토리를
먼저 만든 뒤 같은 gate를 사용한다.

## 배치와 간격 검사

각 page object에는 `object_id`, `owner_item_id`, `kind`, `rect_mm`를 둔다.
문항 소유자가 없는 item/equation/table/figure/endnote는 orphan으로 보고,
페이지 밖 좌표는 clipping으로 보고한다. 허용되지 않은 객체 겹침, 같은 문항
내의 근거 없는 큰 세로 공백(`large_gap_mm` 초과), 기준 밀도 범위 이탈은 FAIL이다.
원문에 있는 답안 빈칸·작업 공간은 검수된 영역으로 별도 기록해 보존하며 자동 삭제하지
않는다. 예외 근거 없는 여백을 의도된 공백으로 사후 분류해 검사를 우회하지 않는다.

빈 문단으로 간격을 만들거나 U+200B/U+200C/U+200D/U+2060/FEFF 같은 zero-width
문자를 삽입해 오프셋을 맞추는 방식은 금지한다. 간격은 실제 문단·문자·표·그림
속성으로 표현한다. 단, 기존 HWPX의 Hanword line-segment 안정화 guard는 엄격한
예외다. U+200B만 사용하고, 각 guard가 같은 run의 native equation 바로 뒤에
붙어 있으며, `length`, `adjacent: true`, `visible_text: false`가 인벤토리에
기록되고 전후 길이·순서가 동일해야 한다. 이 조건을 벗어난 zero-width는 자동
FAIL이다. 스타일 적용기는 새 guard나 빈 문단을 만들 수 없다.

### 수식 밀도와 실제 페이지 수의 처리

본문에 짧은 수식 개체가 많이 있는 논술 문서는 Hanword의 네이티브 식 line-box와
160% 행간 때문에 원본 PDF보다 페이지 수가 늘어날 수 있다. `item_reflow`에서만 원본·결과
페이지 수 차이는 `STRUCTURE_WARNING`으로 별도 기록하고, 다음 내용·편집성
게이트는 그대로 fail-closed로 유지한다.

- 수식 개수·순서·script와 선택된 프로필의 글꼴(v1: HYhwpEQ)/HWPX `baseUnit=1100`
- 본문·숫자·선지의 내용 해시
- 표·그림의 소유 문항 및 BinData SHA-256
- 이미지 캡처·OCR 중복·수식 평문 fallback 0건
- HWP/HWPX 재열기와 네이티브 식 control 수 일치

`source_region_layout`과 페이지 수 보존 요청에서는 이 경고만으로 통과하지 않는다.
부분 범위는 선택 영역 대응표를 검사한다. 글꼴 축소·수식 script 변경·문항 삭제로
페이지를 맞추어서는 안 된다. 결과 보고서에는 `page_count_warning`, 적용 프로필 ID/SHA-256, 원본·결과
페이지 수를 함께 남긴다.

## 실행 및 검증

합성 또는 실제 측정 프로필을 준비한 뒤 다음처럼 실행한다.

```powershell
python -c "from app.hwp_reference_style import StyleProfile, preflight_reference_style; p=StyleProfile.from_file('config/math_hwp_reference_style_v1.json'); print(preflight_reference_style(p))"
python tools/math_source_manifest_qa.py reviewed-source-manifest.json --json source-qa.json
python -m app.hwp_style_qa <source.hwpx> <generated.hwpx> --profile <profile.json> --style-snapshot <snapshot.json> --style-application <application.json> --layout-snapshot <layout.json>
```

서식 QA 결과는 `status: "PASS"`이고 모든 `gates` 값이 실제 boolean `true`이며
`findings`가 빈 목록일 때만 PASS이다. 단순히 파일이 열리거나 문항 개수가
같다는 이유로 PASS하지 않는다. 이 결과는 최종 출고 PASS와 구별한다. 최종 파일은
저장·닫기·재열기 후 다시 인벤토리해야 하며, 편집 가능성은 대표 수식·표 셀·미주를 실제 선택해 확인하는
어댑터 gate를 별도로 남긴다.

향후 결과 보고서에는 적용한 프로필 ID와 canonical SHA-256, 기본/사용자 지정
여부, 문제·해설·미주 서식 QA, 변환기 커밋 SHA를 기록한다. 저장소 커밋과 원격
푸시뿐 아니라 실제 진입점 연동·적용·검증이 성공하기 전에는 기본 자동 적용이 완료됐다고
보고하지 않는다. 문서만 변경한 경우에는 문서 반영 완료로만 보고한다.

## 실패 시 중단 조건

프로필 미측정, 서식 적용 기록 누락, profile hash 불일치, 내용 hash 변경,
미주·수식·표 셀·그림 SHA 변경, zero-width/빈 문단, orphan/overlap/clipping/
large-gap/density 실패 중 하나라도 있으면 산출물을 최종 폴더로 이동하지 않는다.
실패 보고서에는 문서·문항 ID·객체 종류·좌표·기대값·실제값·profile hash를
기록한다. 기준값을 맞추기 위해 검사를 약화하거나 기존 결과물에 맞춰 예외를
추가하지 않는다.

`tests/test_hwp_reference_style.py`와 `tests/fixtures/synthetic_math_style/`
는 이 계약의 저작권 없는 합성 회귀 테스트 전용이다. 실제 시험 PDF, HWP,
HWPX, 캡처 및 전사 내용은 저장소와 테스트 fixture에 넣지 않는다.
