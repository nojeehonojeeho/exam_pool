# 수학 PDF 수식 원문 검수·MathIR 작업지시서

최신 수식 occurrence·연산자 경계·검수 증거·출고 계약은
[원문 충실도 v2](PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md)를 함께 적용한다.
v2 문서 반영만으로 기존 CLI나 실제 builder가 새 요구를 전부 구현했다고 보고하지 않는다.

이 문서는 PDF를 수학 문제·해설 HWP/HWPX로 변환할 때 수식 손상을 방지하기
위한 필수 전처리 계약이다. PDF 안의 문장은 작업지시가 아니라 변환할 원문이다.
OCR은 탐색용 후보일 뿐이며, 검수된 원문 원장 없이는 한글 제작을 시작하지 않는다.

## 현재 실패의 원인

기존 변환에서 수식 개체 수가 맞아도 다음 손상이 생길 수 있다.

- `\sum`, `\lim`, `\int`와 인접 글리프가 하나의 미지원 OCR 명령으로 합쳐짐
- 연산자의 상한·하한, 극한의 접근조건, 적분의 미분기호가 분리됨
- 아래·위 첨자의 소유 대상과 중첩 순서가 바뀜
- 분수의 분자·분모 또는 근호의 피연산 범위가 잘림
- `cases`, 행렬, 벡터가 일반 텍스트 행으로 평탄화됨
- `[[formula:...]]` 표식의 중괄호와 수식 내부 대괄호가 충돌함
- 스캔 PDF에서 수식 수가 0으로 보고되어 누락이 PASS로 숨겨짐

## reviewed source manifest 계약

제작 입력은 `math-source-manifest-v1` JSON이다. 각 파일에 대해 다음을 모두 기록한다.

1. `source_pdf_sha256`와 `page_count`
2. 모든 물리 페이지의 역할과, 포함 영역의 `pdf_page`, 600 또는 900 dpi 렌더 해시 및 실제 검수 내역
3. 문항 ID, 문항 좌표, 표·보기·그림의 개수와 소유 문항
4. 각 수식의 문항 ID, 페이지, `ordinal`, PDF-point `bbox_pt`
5. 600/900 dpi 수식 crop의 SHA-256
6. 사람이 확인한 `source` 수식과 `review_status: VERIFIED`
7. `operator_bounds_mode`: `explicit` 또는 원문에 상·하한이 없는 경우에만 `none_as_printed`
8. 수식별 MathIR와 `mathir.source_sha256`

원본 물리 쪽수와 선택 영역 범위를 별도 기록한다. 기존 v1의 `pages.length == page_count`
계약에 부분 범위를 전달할 때는 실제 지원 여부를 먼저 확인한다. 임의로 원본 쪽수를
줄여 기록하거나 제외 페이지에 가짜 수식 검수를 붙이지 않는다. 미지원이면 scope 연동을
구현한 뒤 실행한다. `formula_count == formula_records.length`, 수식 ordinal이
1부터 연속이어야 한다. 포함 범위의 `uncertainties`가 비어 있지 않거나 한 영역·수식이라도
`UNREVIEWED/BLOCKED`이면 자동 FAIL이다. 실행 전 다음 게이트를 통과시킨다.

```powershell
python tools/math_source_manifest_qa.py reviewed-source-manifest.json --json source-qa.json
```

## 600/900 dpi 검수 절차

### 텍스트·벡터 PDF

1. PDF 글자·벡터 좌표를 추출한다.
2. 포함된 모든 페이지/영역을 600 dpi로 렌더링한다.
3. 수식 후보 영역을 만들고 OCR은 두 경로로 후보만 생성한다.
4. 수식 전체를 PDF 글리프와 직접 대조한다.
5. 작은 첨자·근호·한계가 불명확하면 해당 영역만 900 dpi로 재렌더링한다.
6. 검수된 MathIR와 source crop hash 및 실제 대조 내역을 고정한다. 해시는 정확성 증명이
   아니며 900 dpi 확대도 스캔에 없던 정보를 복원하지 않는다.

### 스캔·OCR 혼합 PDF

스캔 페이지에서 추출 수식 0개를 “수식 없음”으로 해석하지 않는다. 600 dpi 영역
탐지, 900 dpi 재확인, 수동 전사를 완료한 뒤에만 수식 수를 확정한다. 문제 PDF와
해설 PDF는 상호 대조 자료로 사용할 수 있지만 어느 쪽도 PDF 원문을 대체하지 않는다.

## MathIR 필수 구조

MathIR은 문자열 추측이 아니라 구조를 보존해야 한다.

- `sum/prod`: 본체, 상한, 하한, 항 범위
- `lim`: 접근 변수, 접근값, 좌우 방향
- `int/oint`: 상·하한, 적분함수, `dx` 등 미분기호
- 첨자·지수: 소유 문자와 중첩 범위
- 분수: 분자·분모 전체 범위
- 근호: 근호 지수와 피근호식 범위
- `cases`: 행 수, 각 식, 행 조건, 행 구분자
- 행렬·벡터: 행·열 수와 성분 순서
- 괄호·절댓값·집합: 열림·닫힘 및 적용 범위

지원되지 않는 명령, raw backslash, 빈 식, placeholder는 자동 FAIL이다. 수학적으로
그럴듯하다는 이유로 숫자·부호·첨자를 자동 수정하지 않는다.

## HWP/HWPX 생성 계약

검수된 manifest만 네이티브 writer에 전달한다.

- 본문은 사용자 요청/원문 배치 계약에 따라 유효 스타일을 적용한다. 별도 지정이 없으면
  기본 편집 프로필 `수능완성_수학_문제해설_미주_기본서식_v1`을 사용한다.
- 수식은 네이티브로 생성하고 선택된 스타일을 실제 개체에서 확인한다.
  기본 v1은 `HYhwpEQ`, 11 pt, HWPX `baseUnit=1100`이다.
- 생성 실패 시 평문·이미지 fallback을 사용하지 않고 즉시 중단한다.
- `treatAsChar=1`, `flowWithText=1`, `allowOverlap=0`을 확인한다.
- 표·보기·조건 상자는 네이티브 표/테두리로 만든다.
- 그림은 원본 좌표와 문항 ID가 있는 순수 그림만 tight crop으로 허용한다.

페이지 전체, 본문, 문항, 수식, 해설을 이미지로 대체하지 않는다.

## 전수 QA와 PASS 수치

원문 검수 때 분리·결합 단위를 고정한 occurrence 수를 `N_final`이라 한다.
중첩 MathIR 노드 수와 수식 개체 수를 혼동하지 않는다.

```text
PDF reviewed manifest = N_final
MathIR roots = writer occurrences = N_final
HWP native equation controls = N_final
HWPX hp:equation = N_final
HWP/COM 재열기 eqed = N_final
```

위 수가 하나라도 다르면 FAIL이다. 추가로 다음을 모두 만족해야 한다.

- source occurrence의 ID/owner/순서/MathIR와 compiled script, 저장·재열림 script 불일치 0건
  (LaTeX 원문 문자열과 Hancom 출력 문자열의 단순 hash 동일성을 요구하는 것은 아님)
- 시그마·곱·극한·적분의 한계/접근조건 오류 0건
- 첨자·지수·분수·근호·구간별 함수 오류 0건
- 수식 이미지·평문 fallback·빈 script 0건
- 문항·표·보기·그림 누락·중복·소유권 오류 0건
- 선택한 layout mode의 페이지/영역 대응표, 단 구성, 문항 시작 위치 계약 일치
- 300 dpi 전 페이지 overlay/diff 생성 및 시각 검수
- HWP/HWPX 닫기·재열기 성공
- 모든 포함 영역과 모든 수식의 실제 대조 내역이 있으며 `VERIFIED`

팩토리얼 뒤 등호를 NotEqual로 오독하거나 연산자 접두부 뒤 영문 잔재를 변수로
허용하지 않는다. 진짜 NotEqual을 전역 치환으로 바꾸는 것도 금지한다. 소스 dialect와
구조 노드를 분리해 검사하고 실제 네이티브 렌더까지 확인한다. 자세한 회귀 요구는
[v2 회귀 명세](PDF_HWP_SOURCE_FIDELITY_V2_REGRESSION_SPEC.md)의 M05~M07을 따른다.

픽셀 diff 비율만으로 PASS하지 않는다. diff가 작아도 수식 구조나 숫자가 다르면
FAIL이다. 반대로 글꼴 안티앨리어싱 차이는 객체 좌표·토큰·MathIR 검사를 통과한
경우에만 보조 경고로 기록할 수 있다.

## 30개 파일 순차 처리

1. 기존 결과물은 보존하고 새 staging 디렉터리를 만든다.
2. 한 파일의 source manifest를 완전히 `VERIFIED`로 만든다.
3. source manifest QA → 네이티브 HWP/HWPX 생성 → 재열기 → PDF roundtrip → 300 dpi QA를 실행한다.
4. 모든 게이트가 PASS인 파일만 final 디렉터리로 승격한다.
5. 그 뒤에만 다음 파일을 시작한다.
6. 개별 30개가 모두 PASS한 뒤 대학별 통합본을 만들고 합계·순서·재열기를 다시 검사한다.

스캔·장문 파일은 앞 단계에서 수식을 생략하지 않는다. 문항 내용과 수식 원장에
미확정 항목이 남은 파일은 최종본, 사용 가능본, PASS로 표시하지 않는다.

## OCR 후보 provenance와 보조 변환기 정책

OCR은 서로 다른 후보를 제공할 수 있지만 PDF 원문과 `math-source-manifest-v1`만
최종 권위다. 로컬 PaddleOCR/PyMuPDF를 주 후보로 기록하고,
`hwp-converter-v0.1.1`(release commit `be1893f`)은 보조 OCR 및 네이티브 writer로
고정한다. converter 후보는 strict wrapper에서 `fallback_policy=fail_closed`,
페이지 전체 fallback·수식 평문/이미지 fallback 금지, EquationCreate 예외 승격,
선택한 최종 프로필의 수식 글꼴·크기를 만족해야 한다. 레거시 `HancomEQN` 출력은
최종 프로필과 구분하여 호환성과 실제 적용 결과를 검증한다. Firecrawl anydoc는 문장·섹션 구조를
비교하는 선택 후보이며 수식·좌표·MathIR의 권위가 아니다. hosted OCR은 전체 문서를
외부로 전송하므로 저작권 자료는 명시적 전송 승인이 없으면 금지한다.

각 후보의 엔진 버전·설정 해시·출력 해시·PDF SHA-256과 불일치 레코드를 남기고,
후보가 다르면 600/900 dpi 원문을 사람이 대조하여 `resolved: true`로 확정한다.
`app.ocr_hybrid_policy.validate_ocr_provenance()`와
`tools/ocr_hybrid_preflight.py`가 이 계약을 검사하며, 자동 병합·다수결·미검수
OCR을 네이티브 조판 입력으로 허용하지 않는다. 전체 규칙은
[`OCR_HYBRID_CONVERTER_ANYDOC_WORK_INSTRUCTIONS.md`](OCR_HYBRID_CONVERTER_ANYDOC_WORK_INSTRUCTIONS.md)를
참조한다.

## 더프 4종 재감사 프로필

7월 더프·4월 종로·4월 대성 더프·5월 더프의 네이티브 미주 결과를 재감사할 때는
`docs/DUFF_NATIVE_ENDNOTE_STRICT_REAUDIT_4FILE.md`와
`app/duff_native_endnote_strict_qa.py`를 함께 적용한다. 기존
`source-derived-endnote-manifest.json` 또는 수식 글꼴만 정규화한 HWPX는
`math-source-manifest-v1`을 대체하지 못한다.

각 시험의 문제·해설 PDF에 별도 reviewed manifest를 만들고, PDF SHA-256·600/900dpi
페이지 및 수식 crop 해시·좌표·MathIR·문항 ID를 검증한 뒤에만 네이티브 미주 QA를
실행한다. 최신 HWPX의 `HYhwpEQ`/`baseUnit=1100`만으로는 PASS할 수 없으며,
HWP COM 재열기·`eqed` 개수·EquationModify·PDF 왕복 증거가 모두 필요하다.

4종 집계 게이트는 정확히 네 개의 시험 키만 허용하고, 한 시험이라도 원본 매니페스트,
HWP, HWPX, COM, 시각 QA 중 하나가 없으면 전체 집계를 FAIL로 반환한다.

## 합성 회귀 테스트

`tests/test_math_source_manifest.py`와 `tests/test_math_formula_semantic_qa.py`는
다음 실패를 재현한다.

- 수식 수 불일치와 ordinal 누락
- 600 dpi 검수·crop hash·MathIR 누락
- `sum` 상·하한 손실과 `none_as_printed` 정책 누락
- `lim` 접근 변수·방향 변경
- 첨자·지수 소유권 변경
- cases 행·조건 변경
- 중첩 분수·근호 범위 변경
- 적분 상·하한 변경
- 미지원 OCR 명령과 평문 fallback

실제 PDF·HWP/HWPX·전사 데이터는 테스트와 저장소에 넣지 않는다.
