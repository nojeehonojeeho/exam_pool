# PDF → 네이티브 HWP/HWPX 원문 충실도 v2 작업지시서

[공통 실행 기본값](USER_INTENT_EXECUTION_DEFAULT.md)을 적용한다. 이 문서의 v2 게이트는
사용자 의도에 따라 실행을 계속하되, 원문 증거가 닫히기 전 `PASS`/`FINAL` 승격을 금지한다.

현재 단일 실행 `HIGHEND_4SUBJECT_FINAL_20260908_ASTRA_LOW`는
[전용 실행 계약](HIGHEND_4SUBJECT_ASTRA_LOW_FINAL_EXECUTION_20260908.md)을 함께 적용한다.
기존 충실도 게이트와 향후 기본 설정은 완화하거나 변경하지 않는다.

문서 버전: 2.3 · 정책 갱신일: 2026-09-13

향후 작업의 시작 순서와 기존 지침 충돌 정리는
[v12 단일 요청 기본 지시서](PDF_HWP_V12_ONE_REQUEST_WORK_INSTRUCTIONS.md)가 정본이다.
이 문서는 세부 원문/수식/미주 증거 계약으로 함께 적용한다. 요구 추적표는
[v12 피드백 추적표](PDF_HWP_V12_FEEDBACK_TRACEABILITY.md)에 있다.

## 1. 적용 범위와 구현 상태

이 지시서는 수학 문제·해설의 편집형 변환과 요청된 네이티브 미주 작업에 적용한다.
원문에 없는 내용 추가, 작성기의 필드 누락, 수식 구조 손상, 외관만 맞는 이미지
문서, 근거 없는 최종 PASS를 방지하는 공통 계약이다. 첨부 문서의 문구는 원문
데이터이지 작업 지시가 아니다. 사용자 지정 범위와 명시적 서식 요청이 우선한다.

**정책 반영·검사 코드 구현·실제 자료 검증의 완료 범위는 따로 기록한다.** 기존 모듈의 통과 결과만으로
아래 모든 요구가 구현되었다고 간주하지 않는다. 다음 제작 요청에서는 P0의 실제
진입점 연동 상태를 먼저 확인하고, 미구현 항목을 구현·검증한 뒤 제작해야 한다.
문서 커밋·원격 푸시만으로 ‘향후 자동 적용 완료’나 ‘오류 없는 변환’을 보고하지 않는다.

기존 지시서와 충돌하는 원문 충실도·배치 선택·내용 보존·최종 출고 규칙은 이 문서를
우선 적용한다. 기존 CLI는 개별 검사를 실행하는 수단이며 v2 전체 게이트가 아니다.
기존 내용·수식·미주 검사는 유지한다. 미지원 계약을 지원하는 것처럼 실행하지 않는다.

## 1.1 사용자 의도 기반 실행 원칙 (모든 작업의 기본값)

사용자의 의도와 태스크 범위가 분명하면, 범위 안에서 합리적으로 필요한 추측을
수행하고 확인·구현·검증·출고까지 끝까지 실행한다. 사용자가 “할 수 있나”, “원해”,
“도와줘”처럼 표현하더라도 문맥상 PDF 변환·문서 수정·미주 작업·오류 해결을
요청하는 실행 문맥이면 실행 지시로 간주한다. 능력 확인 질문이나 계획만 제시하고
멈추지 않으며, 안전한 범위의 작업은 별도 승인을 기다리지 않고 이어간다.

이 원칙은 다음의 제한을 약화하지 않는다.

- 원본에 없는 문장·수식·선지·정답을 추측해 생성하지 않는다. 원문 근거가 부족한
  부분은 `evidence-open`으로 남기고, source evidence가 닫히기 전 writer에 넘기지 않는다.
- 파괴적 삭제·덮어쓰기·강제 프로세스 종료·외부 권한이 필요한 변경은 사용자의
  명시적 범위와 안전한 복구 경로가 없는 한 수행하지 않는다. 막히면 대체 경로,
  체크포인트, 원인 기록을 남기고 가능한 독립 작업을 계속한다.
- 실제 제작 요청은 `원본 범위 확인 → 문항 단위 재구성 → 네이티브 작성 → 저장·재열림
  → 원본 대조·시각·복사/이동·미주 QA → 출고` 전체를 뜻한다. 일부 단계만 수행한
  후보를 FINAL 또는 PASS로 승격하지 않는다.
- 문맥이 “설계/보고만”으로 제한된 경우에는 쓰기·제작을 추측해 실행하지 않는다.
  반대로 “제작·수정·반영·완료”가 요청되면 계획 보고로 대체하지 않는다.
- 불확실성은 질문으로 무한히 되돌리지 말고, 확인 가능한 원본·기존 체크포인트·
  동일 작업의 검증 결과를 근거로 보수적으로 결정한다. 결정 근거와 영향 범위는
  실행 기록에 남긴다.

이 원칙은 향후 모든 PDF→HWP/HWPX 및 네이티브 미주 작업에도 적용한다. 다만
최종 PASS는 여전히 원본 대조, 내용·수식·배치·COM 재열림·미주 연결 및 전수 시각
검증이 모두 닫힌 경우에만 부여한다.

## 2. 분리해야 할 네 계약

| 계약 | 기록할 내용 | 혼동하면 안 되는 것 |
|---|---|---|
| ContentScope | 사용자 범위, 모든 물리 페이지 역할, 포함/제외 영역, 읽기 순서, 문제·해설 대응 | 전체 책 쪽수와 부분 출력 쪽수 |
| SourceItemIR | 원문 문장·조건·질문·선지·표·그림·수식·빈칸의 구조와 소유 문항 | OCR 후보나 과거 VERIFIED를 원문 자체로 취급 |
| SourceLayoutProfile | 페이지별 규격, 단, 원문 영역 좌표, 상대 순서, 의도된 공백 | 모든 책에 공통 B4 강제 적용 |
| EditableStyleProfile | 확인한 글꼴·크기·문단·개체 속성과 출처, 적용 우선순위 | 선택한 편집 글꼴을 원본에서 측정한 글꼴로 보고 |

이 명칭은 설계 계약이며, 동일 이름의 새 클래스/API가 구현되었다는 선언이 아니다.
각 계약의 버전과 SHA-256, 실제 구현 스키마와의 매핑을 실행 기록에 남긴다.

검사는 반드시 두 방향으로 분리한다.

1. **원본 → 검수 원장:** 원문과 전사·구조가 맞는지 직접 대조한다.
2. **검수 원장 → 작성·저장·재열림 결과:** 확인된 내용이 빠짐없이 보존되었는지 추적한다.

두 번째 검사만 통과하면 잘못된 전사를 정확히 복제할 수도 있다. 개체 수, 해시,
OCR 유사도, VERIFIED 문자열은 첫 번째 검사를 대신하지 못한다.

## 3. 범위 확정과 원문 증거

- 모든 물리 페이지는 포함/제외 역할을 조사하되, OCR·정밀 수식 검수는 포함 영역에
  한정한다. 개념+문제 혼합 페이지에서는 문제 영역만 선택한다. 전체 책 OCR 후
  사후 삭제하지 않는다. 사용자에게 필요 없는 개념·표지·정답을 문제에 넣지 않는다.
- 문항 ID는 책·단원·세트·인쇄 번호·반복 출현 구분을 포함한다. PDF 물리 쪽,
  인쇄 쪽, 문항 전역 순번을 별도 보관한다. 문제 첫 문장과 해설 대상 내용도 대조한다.
- 문제 전용 요청에는 해설을 강제하지 않는다. 문제+해설 또는 미주 요청에는 해설
  연속 영역, 답, 보충 설명까지 소유 ID와 순서를 확정한다.
- 해설과 일반 개념이 섞인 페이지도 영역별로 판단한다. 같은 페이지에 있다는 이유로
  `핵심개념`, 일반 참고 도식, NOTE·자기평가 칸을 해당 문항의 풀이로 자동 편입하지
  않는다. 반대로 제목에 `참고`, `why`, `how`가 있다는 이유만으로 제외하지 않는다.
  본풀이가 참조하거나 해당 문항의 조건·계산을 설명하는 보충 설명과 다른 풀이는
  포함한다. 포함/제외 원장에 원본 페이지·영역·소유 문항·판단 근거·관련 본문 참조를
  기록하고, 판단 불명확 영역은 삭제가 아니라 evidence-open으로 남긴다.
  해설의 중복 문제 재인용은 새 문항으로 세지 않되, 그 위에 추가된 설명·표시의
  의미는 대응 풀이에 보존한다. 옛 원장의 블록 수나 그림 목록은 범위 확정 증거가
  아니며, 제외한 일반 도식을 '원문 그림 누락 0건' 검사에서 무조건 실패시키거나
  포함해야 할 도식을 설명문으로 대체해서 통과시키지 않는다.
- 각 포함 영역과 수식에 원본 SHA-256, PDF-point bbox, 읽기 순번, 600dpi 렌더/crop
  해시를 연결한다. 작은 첨자·한계·선 등이 불분명하면 해당 영역을 900dpi로 확인한다.
  확대 렌더는 스캔에 없던 정보를 만들지 않는다. crop 해시는 재현성 증거이며 정확성
  증명은 아니다. 판독 불가 부분은 위치·대조 내역·불확실성을 남긴다.
- 검수 기록에는 실제 본 영역, 검수자/검수 실행 식별자, 시점, 판정, 미해결 항목을
  남긴다. 자동으로 모든 페이지를 VERIFIED 처리하거나 동일 원장에서 복제한 두
  목록을 독립 검수 증거로 쓰지 않는다.
- 원본이 있고 검수 원장이 없으면 원장 작성·대조 작업 큐로 보낸다. 이를 원본 파일
  부재라고 보고하거나 원본을 다시 요구하며 끝내지 않는다. 미검수 문항은 writer에
  넘기지 않고, 승인된 부분 체크포인트와 전체 미완료 상태를 구분한다.

## 4. 문항 재구성과 작성기 내용 보존

의미 단위 재구성은 원문 문장을 복원하는 것이지 요약·창작·문제 재설계가 아니다.
OCR의 물리 행을 그대로 한글 문단으로 만들지 않는다. 정상적인 자동 줄바꿈은
문장 분할 오류가 아니다. 실제 문단 경계, 수식 삽입 위치, 조건·질문·선지 순서를
원문 증거로 결정한다. 띄어쓰기는 원문과 언어 단위를 함께 확인하고 기계적으로
모든 OCR 토큰 사이에 공백을 넣거나 제거하지 않는다.

### 닫힌 콘텐츠 스키마와 필드 소비 원장

1. 내용 블록은 명시적 type을 가진 닫힌 스키마로 정의한다. 텍스트, 인라인 수식,
   독립 수식, 조건 상자, 질문, 선지, 표, 실제 그림, 빈칸 등 지원 경로를 명시한다.
   메타데이터는 별도 namespace에 둔다. 알 수 없는 내용 필드는 FAIL이다.
2. 레거시 `text` 블록 안의 `condition_box`, `question`, `table`, `choices` 등은
   버리거나 우선 필드 하나만 선택하지 않는다. 원문 읽기 순서가 있는 명시적 블록으로
   정규화하고, 순서가 불명확하면 원문 대조한다. 텍스트+수식 혼합은 inline run으로
   유지하며 정규화가 불필요한 문단 분리를 만들지 않도록 한다.
3. 내용 JSON pointer → 정규화 block ID → writer 처리 기록 → 실제 저장 개체/문단 ID
   → 재열림 readback을 추적한다. 모든 내용 필드가 정확히 한 번 소비되어야 한다.
   다수 run으로 나뉘는 필드는 명시적 일대다 매핑과 원래 순서로 재결합한 값이 필요하다.
4. 필드 소비율 100%, 미소비·알 수 없는 필드·중복 소비 0건을 요구한다. 내용 개수와
   자기보고 메타데이터만 대조하지 않고 **실제 writer 입력과 출력**을 검사한다.
5. 표는 셀 내용·행열·병합·내부 테두리·셀 읽기 순서를, 조건/보기는 상자 안팎과 후속
   질문을 검사한다. 바깥 표가 존재하는 것만으로 내부 조건 표가 보존됐다고 판정하지 않는다.

주관식에는 원본에 없는 선지를 만들지 않는다. `expected_choice_count: 0`도 원문
확인 근거가 필요하다. 해설 정답이나 인접 문항에서 선지를 가져오지 않는다. 문제에
인쇄된 빈칸 풀이·증명은 문제 내용으로 유지하며 삭제하거나 답을 미리 채우지 않는다.
내용이 이미 원장에 있는데 작성기가 버렸다면 먼저 작성 경로를 고친다. OCR 재실행만으로
작성기 결함이 해결됐다고 보고하지 않는다.

## 5. 배치와 실제 편집성

우선순위는 사용자 명시 요청 → 요청된 원문 영역 배치 → 검증된 기본 편집 프로필이다.
`source_region_layout`에서는 페이지별 실제 폭·높이·회전·단·영역을 사용한다.
첫 쪽의 규격을 전체 책에 복제하거나 공통 B4를 하드코딩하지 않는다. `item_reflow`는
별도 배치 요청이 없을 때 선택 가능한 편집 모드이며 원문 배치와 동일하다고 보고하지 않는다.
부분 범위는 source-page/region → output-page/region 대응표로 검사한다.

- 원본 글꼴을 확인하지 못하면 `unknown`으로 남긴다. 기본 함초롬돋움/HYhwpEQ 11pt 등은
  선택된 편집 프로필 값이지 모든 PDF의 원본 값이 아니다. 글꼴·크기와 원문 규격을 함께
  만족시키기 어렵다면 충돌을 보고한다. 무단 축소·내용 삭제·페이지 이미지 대체는 금지한다.
- 스타일 정의만 조사하지 않는다. 실제 텍스트 run의 charPr/paraPr, 상속/override,
  단위, HWPX `switch`의 유효 분기와 COM readback을 확인한다. 한 wrapper의 서식을
  모든 하위 제목·선지·수식 문단의 실제 서식으로 집계하지 않는다.
- 네이티브 단과 1×2 바깥 표를 구분한다. 표 기반 배치를 2단 설정으로 보고하지 않는다.
  어댑터는 읽기 순서, 넘침, 개체 이동, 복사·붙여넣기, 미주 연결을 시험한 뒤 선택한다.
- 원문의 작업 공간·답안 빈칸·의도된 큰 여백을 영역으로 기록한다. 일반 large-gap 검사가
  이를 삭제하도록 만들지 않는다. 간격은 문단/표/개체 속성으로 구현하고 공백·빈 줄 반복을
  사용하지 않는다. 수식 뒤 조사와 질문의 분리, 양쪽 정렬로 인한 과도한 벌어짐을 점검한다.
- 시각 기준본과 편집 기준본은 별도로 감사한다. 보기 좋은 페이지 이미지 HWP는 외관
  참고로만 유효하다. 본문 텍스트·수식·표를 실제 선택·수정할 수 있어야 편집 기준을 통과한다.
- 원본과 결과는 같은 물리 배율로 비교한다. HWP 내부 용지와 PDF 출력 용지/배율을 모두
  기록한다. 자동 축소 PDF를 내부 용지 일치의 증거로 쓰지 않는다. 전체 포함 페이지를
  렌더·검수하고, contact sheet와 대표 화면은 탐색용이지 전수 검수의 대체물이 아니다.

## 6. 수식 구조와 개체 연쇄

수식의 분리·결합 단위를 원문 검수 때 먼저 확정한다. MathIR의 중첩 AST 노드 수를
네이티브 수식 개체 수로 세지 않는다. 개수를 맞추려고 임의로 식을 합치거나 나누지 않는다.

```text
원문 검수 수식 occurrence
  = MathIR root = 실제 writer occurrence
  = 저장 HWPX equation = HWP COM eqed = 재열림 equation
```

각 occurrence의 ID, 소유 문항/셀/미주, 순번, source span, MathIR 구조, 컴파일 script,
재열림 script, 렌더를 함께 비교한다. PDF 재출력에는 HWP와 같은 개체 모델이 없으므로
PDF에서 eqed 수를 추정하지 않고 동일 occurrence의 보이는 내용·영역을 대조한다.

- 합/곱의 본체·상하한, 극한의 변수·접근값·좌우 조건, 적분의 한계·미분기호를 유지한다.
- 위·아래첨자의 소유 대상, 분수·근호 범위, 절댓값, 함수/수열, 구간별 함수의 행과 조건,
  행렬 차원, 벡터·좌표·점 이름, 의도된 수식 빈칸을 구조로 검사한다.
- 팩토리얼 뒤 등호와 진짜 부등호를 구분한다. 문자열 인접 `!`와 `=`를 `≠`로 오독하지
  않도록 Factorial/Equal 노드를 분리한다. 반대로 모든 `!=`를 일괄 치환해 원문의 실제
  NotEqual을 바꾸지 않는다. 소스 dialect를 확정하고 출력 문법에 맞게 컴파일한다.
- 연산자 이름 일부만 변환된 뒤 남은 영문을 변수로 허용하지 않는다. 교집합 등의 연산자는
  닫힌 명령 매핑·구문 분석·원문 대조로 확인한다. 명령 접두부 인식만으로 성공 처리하지 않는다.
- 수식 평문·이미지 fallback, 빈 script, 미지원 명령, 임의 괄호 보완, 불확실 구조는 FAIL이다.
  문법이 유효하고 개수가 같아도 수식이 정확하다는 증거는 아니다.

### 6.1 수식 평문 fallback의 별도 차단

저장된 HWPX의 `hp:equation/hp:script`만 검사해서는 수식이 완전히 네이티브라는
뜻이 아니다. 같은 문단·run의 `hp:t`에 `\\bar{X}`, `\\sum`, `\\lim`처럼 수식
명령이나 구조 토큰이 그대로 남아 있으면, 뒤에 정상 equation 개체가 따라와도
원문 수식이 평문으로 중복·분리된 손상으로 판정한다.

- 모든 section 및 endNote XML에서 **직접 자식 문단의 `hp:t` 텍스트**를 수집하고,
  중첩 표 조상 때문에 같은 문단이 중복 집계되지 않도록 한다.
- 수식 명령 후보가 보이는 텍스트는 `FORMULA_RAW_BACKSLASH_TEXT`로 기록하고,
  문단 번호·전체 표시 텍스트·문서 역할·문항/미주 소유자를 원장에 남긴다.
- 해당 수식의 원본 PDF crop/MathIR와 출력 equation occurrence를 먼저 대조한다.
  원문에 있는 인라인 수식이면 평문 조각을 삭제·요약하지 말고 같은 위치에 네이티브
  equation을 삽입한 새 HWPX/HWP를 만든다. 원문 근거가 없으면 임의로 복원하지
  않고 `evidence-open`으로 차단한다.
- raw `hp:t` 검출 1건이라도 `NativeEditability`와 `SourceFidelity`를 FAIL로
  두며, 수식 개수·글꼴·XML 문법 PASS나 기존 VERIFIED만으로 해제하지 않는다.
- repair 도구는 입력 HWPX를 보존하고 새 파일로만 출력하며, 목표 span이 정확히
  한 번일 때만 동작해야 한다. 수리 후 같은 strict audit와 HWP COM 재열림을 다시
  실행한다.

## 7. 표·그림과 이미지 감사

그림 설명문·관계 목록·`native_semantic` 표시는 검수 메타데이터일 뿐 실제 그림이 아니다.
원문에 그림이 있으면 검수된 네이티브 선/곡선/도형/라벨 또는 허용된 순수 그림 crop이
실제로 있어야 한다. 일반 표가 아닌 도형을 설명 표로 대체하지 않는다.

이미지는 순수 그래프·기하·재작성하기 어려운 순수 삽화 및 범위에 포함된 제한적 장식만
예외로 둔다. 문장·정답·풀이·수식·표·페이지 캡처를 대체물로 쓰지 않는다. 그림 안 라벨·
좌표·수치·선 끝이 원문과 같고 잘리지 않았는지 전수 대조한다. bbox 밖 잉크나 경계 잘림이
의심되면 재검수한다. 장식에는 문항 소유자 대신 명시적 문서/구역 소유자를 기록한다.

모든 실제 본문·미주 이미지의 파일/hash/크기/소유자/원본 bbox/사용 사유/허용 여부와
XML 참조를 기록한다. 문서 미리보기 thumbnail처럼 본문에 삽입되지 않은 패키지 메타
자원은 별도로 분류해 본문 페이지 캡처로 오탐하지 않는다. 70% 면적 미만이라는 이유로
본문 캡처를 허용하지 않는다. 그림 0개 역시 원본 그림 누락 여부를 검사해야 한다.

## 8. 체크포인트와 최종 출고

한 번의 변환+미주 요청은 허용하되 내부 검증을 생략하지 않는다.

```text
범위·원문 증거 → 문항 IR/필드 보존 → 편집형 문제·해설 체크포인트
              → 체크포인트 전수 QA → 요청된 네이티브 미주 → 최종 QA → 패키징
```

미주 전 문제/해설은 원문 충실도·편집성·배치를 검증하고 hash로 고정한다. 번호 바로 뒤
실제 미주 참조 하나를 넣으며 정답·해설 문장·수식·표·그림·보충 설명을 연결한다.
문제 수=해설 수=미주 참조 수=미주 본문 수, 잘못된 연결·중복·누락 0건을 요구한다.
미주 삽입 전후 문제 내용과 대응 해설 내용의 fingerprint를 비교한다.

HWP와 HWPX 각각 저장·닫기·재열림, 전수 구조 readback, 모든 대상 페이지 렌더를
검사한다. 별도 검사용 사본에서 텍스트/수식 직접 수정과 문항 복사·이동 후 미주 추적을
실행하고 확인한 범위를 기록한다. 일부 편집 시험을 모든 문항의 원문 검수로 보고하지 않는다.

| 독립 판정 | 필수 근거 |
|---|---|
| SourceFidelity | 원문 ↔ 전체 내용/수식/도표/빈칸 검수 및 불확실성 0 |
| NativeEditability | 실제 텍스트·수식·표·개체 readback, 직접 편집 시험, fallback 0 |
| Layout | 선택 모드/프로필, 전 페이지 배치·잘림·겹침·순서·유효 서식 검수 |
| EndnoteLinkage | 미주 요청 시 전수 대응/내용 보존, 재열림·복사·이동 시험 |
| ArtifactLineage | 검수 입력·실행 코드·저장/재열림 파일·출고 파일의 해시 연결 |

미주가 요청되지 않았다면 EndnoteLinkage는 근거 있는 `NOT_APPLICABLE`로 기록하고
미주 0개를 확인한다. 누락된 검사를 NOT_APPLICABLE로 처리하지 않는다.

각 게이트의 FAIL/BLOCKED/UNVERIFIED/REVIEW_REQUIRED/누락은 최종 PASS를 막는다.
`build_status`, XML/수식 문법 검사, 서식 검사, 체크포인트, `release_status`를 구분한다.
수식 개수·글꼴 PASS나 과거 VERIFIED, `source_fidelity=false`를 후처리로 최종 PASS로
승격하지 않는다. status JSON 수동 수정과 패키징 중 상태 승격은 금지한다.

현실적 한계가 있어 사용자가 후보 제공을 허용한 경우에만 원본 위치·미검수 범위·알려진
결함을 적은 비최종 후보를 별도로 제공한다. 이 허용은 내용 오류를 숨기거나 PASS 기준을
완화할 권한이 아니다. 결함 수치와 검수 범위를 구분하고 ‘완벽/무오류’를 보장하지 않는다.

## 9. 실제 진입점과 증거 수명

- 실제 호출한 builder/adapter/QA/packager 경로와 버전·SHA-256, 저장소 commit,
  dirty diff hash를 기록한다. 저장소 밖 작업 스크립트도 예외가 아니다.
- 범용 QA가 존재해도 실제 builder가 호출하지 않으면 구현 완료가 아니다. 실제 ordered
  blocks가 preflight를 거치고 저장된 파일이 readback/최종 gate를 거치는 경로를 시험한다.
  별도 가짜 manifest·단독 validator 테스트만으로 실제 제작 경로를 검증했다고 하지 않는다.
- 원본/scope/원장/스타일/컴파일러/builder/출력 hash가 바뀌면 영향을 받는 후속 증거를
  무효화하고 다시 검사한다. 입력·정책 버전과 출력 파일까지 QA report에 묶는다.
- 출고 폴더 복사·이름 변경·압축 이후에도 파일별 SHA-256을 승인된 산출물과 대조한다.
  같은 hash의 기존 파일은 현재 계약을 실제 통과한 재제공이면 허용한다. 오래된 날짜만으로
  실패라고 단정하지 않지만, 새 이름만 붙인 파일을 새로 검수한 것으로 보고하지 않는다.
- 통합본은 승인된 개별본의 내용/수식/도표/미주 소유권·순서를 다시 검사한다. 일부 좋은
  체크포인트를 검증 안 된 전체본과 섞어 최종본으로 제공하지 않는다.

## 10. 다음 구현·제작 요청의 실행 순서

| 순서 | 완료 조건 | 미완료 시 |
|---|---|---|
| P0 작성/출고 경로 | 닫힌 스키마, 누락 필드 추적, 수식 연산자 경계, 실제 진입점 preflight/readback, 해시 결합 출고 검사와 합성 회귀 검증 | 실제 자료 writer 호출 금지; 구현·검수 작업 계속 |
| P1 편집형 문제 | 작은 파일럿의 원문 충실도+실제 편집성+배치 동시 통과, 별도 고위험 유형 시험, 전체 포함 문항 전수 검수 | 실패 문항 수정/재검수, 전체 완료로 확대 금지 |
| P2 해설·미주 | 대응 해설 전체 검수, 미주 전 체크포인트, 요청된 미주 전수 QA, 출고 파일 해시 검증 | 미주 및 최종 승격 보류 |

구현 단위 후보는 SourceItemIR normalizer/schema, field-consumption ledger,
source-region layout adapter, formula compiler boundary checks, evidence-bound release
gate 및 실제 runner/packager 연동이다. 새 파일명·API·CLI 옵션은 구현을 확인하기 전까지
실행 가능한 명령처럼 안내하지 않는다. 회귀 요구는
[합성 회귀 검증 명세](PDF_HWP_SOURCE_FIDELITY_V2_REGRESSION_SPEC.md)에 둔다.

## 11. 보고·저장소 반영

최종 보고에는 포함/제외 범위, 적용 배치 모드, 스타일 ID/버전/hash와 실제 적용 값,
원문 검수 범위, 필드 소비 및 수식 연쇄 수치, 독립 게이트 상태, 이미지 예외,
미해결 항목, 실제 builder/코드 버전, 출고 HWP/HWPX hash를 남긴다.

저장소에는 일반 작업지시서·코드·정책·저작권 없는 합성 fixture만 반영한다. 원본 PDF,
실제 문장·수식 전사·문항 원장, HWP/HWPX, 원문 그림/crop, 화면 캡처, 실제 자료 감사
증거는 로컬에 보존하고 커밋하지 않는다. 문서 반영과 구현·실제 제작·검증·원격 푸시의
완료 여부를 각각 보고한다.

## 12. 진행률·raw finding·root cause의 구분

`scope_item_count`, `reconstructed_item_count`, `evidence_closed_item_count`와
`evidence_open_item_count`를 별도 필드로 기록한다. 예를 들어 `22/106`은 제작된 문항
수가 아니라 원본 영역·문장·수식·특수 블록·해설 대응 증거가 닫힌 문항 수이다.

검수기는 모든 세부 finding을 `raw_finding_count`로 보존한다. raw finding 하나가 실제
독립 오타 하나라는 뜻은 아니다. 같은 원본 증거 미종결 때문에 여러 하위 finding이 동시에
발생할 수 있다.

각 finding에는 보수적인 `root_cause_id` 후보를 붙일 수 있지만, 이는 진단용 집계이며
자동 해결·자동 삭제·PASS 승격에 사용하지 않는다. 문항 ID, semantic block anchor,
오류 범주가 모두 일치할 때만 후보를 묶고, 적분 상한 오독·조건표 행 누락·그래프 라벨
손상·미주 오연결처럼 독립된 내용 오류는 합치지 않는다.

상위 원인을 수정한 뒤 같은 입력 hash와 정책 버전으로 strict validator를 재실행하고,
raw finding이 실제로 감소했는지 확인한다. `evidence_open_item_count > 0`,
`raw release finding > 0`, `release_blocker_count > 0`이면 최종 PASS를 금지한다.
진행률을 줄여 보이게 하거나 finding을 병합하여 게이트를 우회하는 행위는 금지한다.

### 12.1 문항 단위 연쇄와 필수 원장

각 수식은 다음 연쇄를 하나의 occurrence ID로 추적한다.

```text
원본 PDF occurrence → SourceItemIR → MathIR → HWP dialect script
→ writer occurrence → 저장 HWPX equation → HWP COM 개체 → 재열림 equation
```

문항별 원장에는 최소 `finding_id`, `item_id`, `document_role`, `source_page`,
`source_region`, `formula_occurrence_id`, `rule_id`, `stage`, `evidence_key`,
`root_cause_id`, `parent_finding_id`, `source_hash`, `manifest_hash`, `code_hash`,
`severity`, `status`, `resolution_evidence`, `first_seen_run_id`, `last_seen_run_id`를 둔다.

실행 폴더에는 `strict-findings.jsonl`, `root-cause-summary.json`,
`evidence-closure-summary.json`, `formula-occurrence-ledger.jsonl`,
`problem-solution-linkage.json`, `work-queue.json`, `build-and-qa.json`을 남긴다.
원본·manifest·crop·compiler·writer·code hash가 바뀌면 관련 closure와 과거 QA를 무효화한다.

### 12.2 전체본 차단과 검수 작업의 분리

전체본 writer가 차단되어도 evidence-open 문항의 원본 대조·수식·도형·해설 연결 작업은
계속한다. 기존 checkpoint는 입력 hash가 유지되고 최신 v2 재검증을 통과한 경우에만
재사용한다. `VERIFIED_SUBSET` 또는 과거 PASS만으로 전체본 PASS를 만들 수 없다.

checkpoint의 `CHECKPOINT_VERIFIED_NOT_BOOK_FINAL` 상태는 최종 evidence-closed나 PASS가
아니다. 재사용 가능성은 `work/build_checkpoint_closure_candidates.py`가 생성하는
`candidate_only` 원장으로 기록하고, 부모 전체 원장에 다시 연결한 뒤 최신 v2 게이트를
재실행한다. 이 원장은 raw finding을 삭제하거나 evidence-open 수를 줄이지 않는다.

문항 작업은 번호 순서만이 아니라 원본 페이지·단원·수식 root cause·특수 블록 유형별
큐로 묶는다. 일반 문항은 600dpi, 첨자·부등호·분수선·근호 끝·조합 표기·도형 라벨은
900dpi crop을 추가한다.

고정된 B4 용지를 source-fidelity 결과의 기본값으로 사용하지 않는다. 고등학교 교재
builder를 실행할 때는 지원되는 실제 source PDF 인자를 전달해 페이지별 MediaBox/
CropBox/회전/단을 측정하고, 결과 manifest에 `source_geometry.status=MEASURED`, PDF SHA-256 및 pt/mm 값을
남긴다. source PDF가 없으면 해당 산출물은 기하 증거가 없는 legacy 후보로만 보존하며
최종 PASS를 금지한다.

기존 HWP/HWPX의 페이지 설정을 교정해야 할 때는 원본을 덮어쓰지 않고
`tools/normalize_hwp_page_geometry.py`를 사용해 새 출력 디렉터리에 직렬 저장한다.
이 도구는 원본 PDF 전체 MediaBox의 중앙값을 pt→mm로 환산해 모든 section에 적용하므로,
**모든 대상 페이지의 규격/방향이 동일하고 선언한 layout contract와 맞는 경우에만** 쓴다.
혼합 규격·회전 문서는 이 일괄 도구 대신 페이지/구역별 검증된 adapter를 사용한다.
입력·출력 SHA-256과 변경 전후 pageDef를 JSON으로 남긴다. 문제 문서와 통합 미주 문서는
문제 PDF의 기하를, 정답·풀이 문서는 대응 정답 PDF의 기하를 사용한다. 도구의 성공은
페이지 기하 교정 증거일 뿐이며, 원본 내용·수식·미주·COM·시각 게이트를 대신하지 않는다.
페이지 교정 후에는 새 HWP/HWPX를 다시 열어 `PaperWidth`, `PaperHeight`, 방향, 여백을
확인하고 통합 미주 배치 및 source-fidelity 게이트를 재실행한다.

페이지 폭을 교정한 문서에 레거시 2단 조판 표가 포함되어 있으면 표의 절대 폭이 이전
용지 폭을 그대로 유지하여 오른쪽 열이 잘릴 수 있다. 이 경우 새 출력 디렉터리에서
`tools/normalize_hwp_table_widths.py`를 직렬 실행한다. 이 도구는 `pagePr`의 좌우 여백과
제본 여백을 뺀 실제 본문 폭보다 큰 **최상위** 레이아웃 표와 직접 셀 폭만 비례 축소하고,
보기·조건 상자처럼 셀 안에 중첩된 표는 건드리지 않는다. 각 표의 변경 전·후 폭과 입력·출력
해시를 기록하며, 성공은 폭 교정 증거일 뿐 원문 내용·수식·미주·COM·시각 검수를 대신하지
않는다. 표 폭 교정 뒤에는 HWP/HWPX 재열림과 첫·마지막 페이지 300dpi 시각 샘플을 다시
수행하고, 오른쪽 열 잘림·표 경계 겹침이 하나라도 있으면 출고를 차단한다.

### 12.3 진행률 필드와 evidence-open 작업 큐의 엄격한 의미

실행 보고서는 다음 필드를 모두 함께 기록한다.

```text
scope_item_count
inventory_item_count
reconstructed_item_count
legacy_reviewed_scope_count
evidence_closed_item_count
evidence_open_item_count
formula_bearing_item_count
source_formula_occurrence_count
mathir_occurrence_count
writer_formula_occurrence_count
saved_hwpx_equation_count
reopened_equation_count
raw_finding_count
unique_root_cause_count
blocking_item_count
release_blocker_count
```

`legacy_reviewed_scope_count`는 과거에 상세 검토된 범위일 뿐 `evidence_closed_item_count`가
아니다. 과거 검토 문항은 최신 v2로 재검증하여 실제 증거가 닫힌 경우에만 closed로 집계한다.
따라서 예를 들어 “전체 371, 과거 검토 80, 나머지 291”이라는 설명은 작업 큐를 시작하는
참고값일 뿐이며, 80개 재검증 결과에 따라 `evidence_open_item_count`를 매 실행 실제값으로
다시 계산한다. 291을 코드나 보고서에 고정해 evidence-open으로 대체하지 않는다.

`raw_finding_count`는 모든 세부 finding 수이고 `unique_root_cause_count`는 결정적 후보
집계 수이다. `blocking_item_count`는 하나 이상의 미해결 finding이 있는 문항 수이며,
`release_blocker_count`는 최종 출고를 막는 미해결 finding 수이다. root-cause 수가 줄어도
raw finding 또는 release blocker가 남아 있으면 PASS가 아니다.

evidence-open 작업 큐는 문항 번호만으로 정렬하지 않고 원본 페이지·단원·문서 역할·수식
root cause·특수 블록 유형으로 묶는다. 각 큐 항목에는 최소 source page/region, formula
occurrence IDs, 필요한 600/900dpi crop, 문제-해설 대응, 다음 게이트와 `release_eligible=false`
를 기록한다. checkpoint 후보는 `candidate_only=true`로 보존하며, 부모 전체 원장의
evidence-open 수·raw finding 수·release blocker 수를 줄이지 않는다.

각 root cause 후보의 키는 다음 구성요소를 정규화한 값으로 결정적으로 생성한다.

```text
document_role | item_id | stage | evidence_key | source_hash
```

source PDF, scope, manifest, crop, compiler, writer 또는 code hash가 바뀌면 관련 closure와
과거 QA를 자동 무효화하고 큐에 되돌린다. 하위 finding status를 수동으로 CLOSED로 바꾸거나
상위 원인 메모만으로 일괄 종료하는 것은 금지한다.

매 실행 종료 시 `app/v2_execution_report.py` 또는 `tools/v2_execution_report.py`(CLI:
`python tools/v2_execution_report.py <state-dir> --json report.json --md report.md`)로 분리 지표, legacy v2 재검증, 수식
root-cause 상위 20개, 페이지·단원별 큐, strict 재실행, 필수 원장 존재를 재생성한다.
이 보고기는 `291` 같은 과거 scope-minus-legacy 값을 evidence-open으로 대체하지 않고
closure summary의 실제 `evidence_open_item_count`를 사용한다. strict ledger가 있으면
raw finding 수를 ledger 행 수와 대조하고, root-cause는 진단용 후보로만 표시한다.
`FINAL_PASS`는 evidence-open/raw finding/release blocker/blocking item이 모두 0이고
production build 상태가 PASS일 때만 산출된다.

### 12.4 수식 provenance gate와 writer 진입 차단

`audit_authoring_items`의 PASS는 writer 입력의 문법·자산 무결성만 의미하며 원본
충실도를 증명하지 않는다. 실제 production runner는 writer/COM 호출 전에
`app/pdf_hwp_formula_provenance_gate.py`의
`audit_formula_provenance(..., require_source_evidence=True)`를 반드시 실행한다.
다음 필드가 수식 occurrence별로 완료되지 않으면
`FORMULA_SOURCE_EVIDENCE_MISSING`, `FORMULA_SOURCE_BBOX_MISSING`, `MATHIR_MISSING`,
`MATHIR_SOURCE_HASH_MISMATCH`, `DIALECT_REQUIRED` 등의 raw finding을 기록하고 build를
`BLOCKED`로 끝낸다.

```text
source_pdf_verified=true
→ formula_occurrence_id + item_id + source_order
→ source page + positive bbox + 600/900dpi crop SHA-256 + source PDF SHA-256
→ source_text_sha256
→ non-empty MathIR with mathir.source_sha256 == source_text_sha256
→ non-empty writer script + script_language/HWP dialect
```

수식 개수, `review_status=VERIFIED`, HWPX XML 정상, HWP 재열림만으로는 이 게이트를
우회할 수 없다. flat `formula_occurrences` ledger와 typed `problem_blocks`/
`solution_blocks`를 모두 검사하며, occurrence ID 중복·소유 문항 누락·순서 누락도
독립 finding으로 남긴다. 완전한 source provenance가 없는 기존 checkpoint는
`candidate_only`/`evidence_open`으로만 재사용하고 전체본 PASS로 승격하지 않는다.

### 12.5 검수 원장과 작성 원장의 수식 closure

source 검수 원장과 writer 입력 원장은 별도로 보존하고, writer가 만든 수식이
어떤 원본 occurrence인지 자동 추정하여 닫지 않는다. `app/pdf_hwp_formula_closure.py`
의 closure 단계는 다음 순서만 허용한다.

1. source 쪽에 명시적 `formula_occurrence_id`가 있으면 작성 쪽의 **같은 명시적 ID**와
   정확히 일치해야 한다.
2. source 쪽 ID가 없고 양쪽에 `item_id`, `source_order`, `source_text_sha256`가 모두
   있으며 그 조합이 유일할 때만 `exact_composite_key`를 허용한다.
3. source 쪽에는 명시적 ID가 있지만 작성 쪽 ID가 다른 경우에는 composite key로
   우회하지 않는다. `FORMULA_AUTHORING_OCCURRENCE_ID_MISMATCH`와 연결 누락을
   기록하고 `REVIEW_REQUIRED`로 둔다.
4. fuzzy text similarity, 페이지 근접성, 리스트 순번, `VERIFIED` 라벨만으로는
   연결·종료·PASS를 만들지 않는다.
5. item-level crop/page evidence를 개별 수식의 bbox/crop 증거로 상속하지 않는다.
   수식별 bbox, crop SHA-256, DPI는 해당 occurrence record에 직접 있어야 한다.

closure 결과는 `formula-occurrence-ledger.jsonl`과
`evidence-closure-summary.json`에 `match_method`, `closure_status`,
`candidate_only`, `evidence_open_item_count`를 기록한다. 하나라도 미연결·중복·ID
충돌·MathIR hash 불일치·dialect 누락이면 전체 writer 진입과 최종 PASS를 차단하며,
raw finding 원장은 삭제하지 않는다. closure가 PASS가 되더라도 이후 HWPX 저장,
COM 재열림, 문제-해설 미주 연결, 레이아웃 게이트를 별도로 통과해야 한다.

### 12.6 OCR 수식 후보의 과검출 방지

레거시 OCR 원장이나 표·선지 데이터가 이미 `equation` 타입으로 표시되어 있어도
그 값을 그대로 native equation으로 승격하지 않는다. 단독 정수·소수·부호가 없는
상수(예: `6`, `0.5`, `320`)는 원문에서 별도 수식 occurrence라는 증거가 없으면
일반 text run으로 되돌린다. 표 셀의 숫자, 선택지 숫자, 쪽번호, 단계 번호를 수식으로
만드는 것은 원문 충실도 오류이므로 `FALSE_FORMULA_NUMERIC_TOKEN`으로 기록한다.

반대로 등식·부등식·분수·근호·연산식·함수·첨자/지수처럼 수학적 구조가 있는 후보만
수식 occurrence로 유지한다. 후보 승격 뒤에는 `formula_occurrence_id`를 부여하고,
원본의 동일 문항·순번·source text hash와 연결한다. 단독 상수를 text로 되돌린 뒤
formula 개수가 줄어드는 것은 누락이 아니라 과검출 제거일 수 있으므로, 이전 원장과
새 원장의 차이는 `demoted_numeric_equation_count`로 보고하고 raw finding을 삭제하지
않는다. 이 정책은 writer 이전에 적용하며, HWPX equation 개수만 맞추기 위해 임의로
수식을 되살리는 우회를 금지한다.

수식 crop 증거는 occurrence ID별로 정확히 1개 이상이어야 한다. 같은 넓은 문항/열
context crop을 여러 수식이 공유하거나, crop 목록과 현재 occurrence 순서가 어긋난
상태에서 `VERIFIED`를 부여하지 않는다. source PDF hash·페이지·bbox·DPI·crop hash와
실제 열람 기록이 모두 같은 occurrence record에 있어야 provenance gate가 닫힌다.

### 12.7 OCR 행과 의미 문단의 경계

OCR sidecar의 한 행은 물리적인 검출 행일 뿐 문단이 아니다. 작성기는 이를
그대로 `BreakPara`로 출력해서는 안 된다. `SourceItemIR`의 의미 블록과
`paragraph → text/equation runs`를 먼저 확정한 뒤 문단을 만든다. 일반 한글
문장에 수식이 섞인 경우에도 한 문단 안의 inline native equation으로 보존할 수
있어야 한다.

조건·보기 표지는 실제 구분자가 있는 `(가)`, `(나)`, `가)`, `가.` 및 원문에서
확인된 번호 표지만 별도 문단으로 인정한다. `[가-다]`처럼 유니코드 범위를
사용하거나 괄호를 선택 사항으로 둔 정규식은 금지한다. 문장 종결기호·OCR 행 수
상한·수식 검출 여부만으로 문단을 강제 분리하지 않는다. 줄 끝 어절이 다음 행으로
이어진다는 증거가 있으면 하나의 문단으로 복원하고, 원문의 공백·숫자·부호를
임의로 추가/삭제하지 않는다.

설명과 다음 수식이 원문상 종속된 별도 의미 문단이면 후속 블록에
`metadata.keep_with_previous=true`를 명시하고 `bind_solution_flow`로 앞 문단의
`keep_with_next`를 설정한다. 인라인 수식을 담은 텍스트 문단도 같은 대상이다.
어미나 OCR 행 끝만으로 관계를 추정하거나 문장을 다시 쓰지 않는다. 적용 후에는
문제·별도 해설·미주에서 내용 불변을 검사하고, 실제 페이지 경계에서 종속 수식 분리와
과도한 빈 공간이 없는지 재검수한다. 해당 합성 회귀 테스트는
`tests/test_hwp_solution_flow.py`이며 시각 검수를 대체하지 않는다.

해설은 `출제영역` 문자열, OCR 검출 개수, 목록 순서만으로 시작·끝을 추정하지
않는다. 인쇄 문항 번호, 정답 표제, 단원 구획, 실제 시작/끝 bbox와 다단·다쪽
continuation을 함께 기록한다. 기대 개수를 맞추려고 긴 블록을 절반으로 자르거나
빈 문항을 삽입하거나 문제 목록과 `zip` 순서로 대응하는 것은 금지한다. 대응이
닫히지 않으면 해당 writer와 미주를 `EVIDENCE_OPEN`으로 중지한다.

표·조건 상자·선지·그림은 typed block과 소유 `item_id`를 가져야 한다. 원문에서
존재하는데 출력 개수가 0이면 자동 FAIL이다. 수식과 그림 설명문을 서로 대체하지
않으며, 평문/이미지 수식 fallback을 허용하지 않는다.

### 12.8 증거 파일과 출고 게이트의 실행 강제

`document-release-status.json`의 `evidence_files`는 문자열 목록만으로 충분하지
않다. `evidence_root`와 각 증거의 상대경로·SHA-256·run_id·scope_hash·source
PDF/manifest/compiler/writer/artifact hash를 저장하고, 게이트가 실제 파일 존재와
해시 일치를 다시 계산한다. 존재하지 않는 이름, 임의의 `h`/`x` 해시, 다른 실행의
증거는 FINAL을 만들 수 없다. 상태 폴더와 프로젝트 루트의 상대경로를 혼용하지
않고 단일 evidence root를 사용한다.

시각 검수는 `expected_pages`와 `checked_pages` 숫자만으로 PASS가 아니다. 모든
페이지가 정확히 한 번씩 있어야 하고 페이지 번호·렌더 SHA-256·DPI·픽셀 크기·실제
수동 검수 결과를 포함해야 한다. `pages=[]`, 중복/누락 페이지, 자기신고만 있는
`manual_review_completed`는 차단한다. 잉크량 검사는 빈 페이지 보조 검사일 뿐
내용·문단·수식·배치 검수를 대체하지 않는다.

미주 검사는 실제 참조/본문의 문항 ID·번호·내용 fingerprint를 필수로 한다.
`None == None`, 같은 미주 번호의 반복 또는 빈 body fingerprint를 통과 근거로
사용하지 않는다. 문제·해설 단독 문서의 미주 없음은 실제 구조 증거가 있는
`NOT_APPLICABLE`로 기록하고, 통합본에서는 우회할 수 없다.

수식 closure의 `linked_formula_occurrences`는 `match_method`가 존재하는 행이
아니라 `closure_status=CLOSED`이며 실제 `authoring_path`와 MathIR/dialect가
연결된 occurrence만 센다. source manifest 검증 결과가 REVIEW_REQUIRED이면
closure 최상위도 PASS가 아니다.

### 12.8.1 HWP COM 파일 접근 승인 보안 게이트

모든 writer/readback/roundtrip/transfer/postprocess 진입점은
`app/integrations/hwp_security.py`의 `create_secure_hwp()`를 공통 사용한다.
`pyhwpx.Hwp(register_module=True)`만으로 성공했다고 간주하지 않는다.

파일 접근 전에 다음을 순서대로 확인한다.

```text
HKCU\\Software\\HNC\\HwpAutomation\\Modules
  REG_SZ FilePathCheckerModule
  → FilePathCheckerModule.dll 존재·SHA-256·PE 형식·한글 비트수 확인
  → HwpObject.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
  → 실제 반환값 True 확인
```

DLL 또는 레지스트리 검증이 실패하거나 `RegisterModule`이 False이면
`HWP_SECURITY_MODULE_NOT_ACTIVE`로 즉시 종료한다. 승인 팝업을 무기한 기다리거나
화면 좌표 클릭으로 우회하지 않는다. 이미 열린 팝업은 대상이 허용 경로일 때만
사용자가 한 번 해제할 수 있지만, 그것은 영구 해결이나 PASS 증거가 아니다.

한글 COM은 직렬 실행한다. 새 문서 두 개를 별도 파일명으로 저장하고 HWP/HWPX
재열림·PDF 출력·새로 만든 Hwp PID 정상 종료·승인 팝업 0회를 확인한다. 기존
출력물을 덮어쓰지 않는 `work/hwp_security_probe_*`에 증거를 보존한다.
다수의 고아 Hwp 프로세스로 DispatchEx/makepy가 일시 실패할 때만
`PYHWPX_FORCE_STANDALONE=1` 격리 세션을 한 번 재시험하며, 반복 실패는
`REVIEW_REQUIRED`로 남긴다.

현재 검증된 DLL은 x86/PE32, SHA-256
`9AC5B97C47AC8AED1E8BCA27A3EEF39411361D8F68C262509F0C40A8F9D21BB6`이며,
한글 2024 x86/PE32와 일치한다. 상세 절차와 실행 명령은
`docs/HWP_COM_AUTOMATION_SECURITY.md`를 따른다.

### 12.9 후보 문항 수·변형 문항·레거시 검토 수의 분리

후보 manifest의 `items` 또는 `item_count`는 실제 출고 문항 수로 자동 승격하지
않는다. 다음 값을 별도로 기록한다.

```text
candidate_id_count
declared_item_count
legacy_reviewed_scope_count
evidence_closed_item_count
evidence_open_item_count
```

`legacy_reviewed_scope_count`는 과거 원장에 `review_status=VERIFIED`라고 적힌 ID의
수이며, 원본 충실도 증거가 닫힌 문항 수가 아니다. `evidence_closed_item_count`는
문항별 원본 PDF SHA-256, 페이지, bbox, crop SHA-256, 검수 실행 ID와 내용·수식·해설
대응 증거가 함께 있고 `evidence_status=CLOSED`인 동일 ID만 센다. `VERIFIED` 문자열,
현재 HWPX 수식 개수, 출력 파일 존재만으로는 closed가 되지 않는다.

Step B처럼 하나의 인쇄 번호에서 기본문항과 `-1` 변형문항이 함께 나오는 구조는
번호 목록 개수와 실제 item 후보 개수를 따로 기록한다. Step B의 각 번호는 원본에서
확인된 경우 `<번호>`와 `<번호>-1`을 각각 고유 item ID로 확장하고, 두 ID에 페이지,
bbox, 읽기 순서, 해설 대응을 따로 부여한다. 변형을 생략한 목록과 단순히
`item_count`를 두 배로 만든 목록은 정본이 아니다.

범위 재조정기는 후보 ID 집합과 검토 ID 집합의 차이를 `open_ids`로 보고하며, 이를
곧바로 실제 누락 문항 수라고 부르지 않는다. `candidate_id_count`와
`declared_item_count`가 다르면 차이의 산식(변형·소문항·하위 블록)을 기록하고,
실제 문항 수는 원본 페이지·번호·영역 대조가 끝난 뒤 확정한다.

### 12.10 COM 세션 수명·시간 제한·재열림 추적

한글 자동화는 직렬 잠금 아래에서 실행하며, 각 세션에 `run_id`, 소유 PID, 시작 시각,
현재 문서, 마지막 성공 단계, deadline, 생성된 모든 Hwp PID를 기록한다. 문서 최초
생성 PID만 저장하고 재열림 PID를 누락하지 않는다.

COM의 `Open`, `SaveAs`, `Print`, `Close/Quit` 호출에는 단계별 bounded timeout을
적용한다. 반환이 없으면 새 HWP 인스턴스를 병렬로 추가하지 않고, 저장 여부와 복구
파일을 확인한 뒤 격리 세션에서 한 번만 재시험한다. 사용자 또는 출처가 불명확한
Hwp.exe를 이름으로 일괄 종료하지 않는다.

승인창 감시에서 창 목록 조회 실패는 `WINDOW_ENUMERATION_UNAVAILABLE`로 기록하며
승인창 0회로 간주하지 않는다. 승인창 0회 판정은 조회 성공, 등록된 보안 모듈의
`RegisterModule=True`, 허용 경로, 테스트 파일 생성, 재열림, 소유 PID 정상 종료가
모두 있어야 한다.

`skip-com` 또는 XML-only 검사는 COM 재열림 PASS가 아니다. 새 문서 2개를 서로 다른
이름으로 저장하고 HWP/HWPX/PDF를 다시 열어 검사한 뒤, 처음 생성·재열림 과정에서
만든 모든 PID가 bounded wait 안에 종료된 경우에만 COM 보안 시험을 PASS로 기록한다.

### 12.11 표의 중복 빈 문단과 빈 페이지

긴 조건 상자·선지 표의 자동 생성 경로에서 중복 `BreakPara`가 생기면 내용이
한 쪽에 들어가더라도 표 뒤의 필수 문단이 다음 빈 쪽으로 밀릴 수 있다.
이를 글자 축소·여백 임의 변경·PDF 빈 쪽 삭제로 숨기지 않는다.

실제 출력과 HWPX를 대조한 뒤에만 `app/hwpx_reviewed_layout.py`의 명시적
`cell_tails` 또는 `cell_spacers` 계획을 사용한다. 입력 SHA-256, 표·셀 인덱스,
정확한 빈 끝 문단 수 또는 문단 인덱스·기존 문단 모양 ID가 일치해야 한다.
일반 텍스트·공백 문자·수식·미주·책갈피·개행 제어·알 수 없는 개체를 가진
문단은 삭제 대상으로 인정하지 않는다. 셀의 모든 문단을 없애지 않는다.
필수 본문 끝 문단을 일괄 삭제하거나 전체 문서의 빈 문단을 자동 정리하지 않는다.

새 패키지로만 저장하고 본문·표 셀·수식·미주 스냅샷이 보정 전후 같은지 검사한다.
실제 한글 저장·재열림 및 영향 페이지의 렌더 검사로 빈 쪽 제거와 정상 간격을
확인한다. 끝 문단 제거만으로 해결되지 않았다면 같은 보정을 반복하지 말고
표 앞 중복 간격과 실제 가용 높이를 다시 측정한다. 일부 빈 쪽이 없어졌더라도
긴 수식의 단 경계 이탈·문장부호 고립·전체 미주 연결 검수를 생략하지 않는다.

합성 회귀: `tests/test_hwpx_reviewed_cell_tail.py`, `tests/test_hwpx_reviewed_layout.py`.

### 12.12 긴 등식의 검토된 표시 줄 배치

긴 네이티브 등식이 단 너비를 넘으면 글자 축소, 수식 이미지 대체, 항 삭제로 해결하지 않는다.
`app/hwp_equation_line_layout.py`는 원본 dialect 스크립트 SHA-256과 명시적으로 검토한
최상위 등호 순번을 받아 하나의 수식 개체 안에 `eqalign` 표시 줄을 만든다.
괄호 안 등호·인용문·이미 행 구조가 있는 수식은 임의 분할하지 않는다.
원본 스크립트와 MathIR는 유지하고 표시 스크립트, 줄 분할 계획, occurrence ID를 별도로 연결한다.
이 헬퍼는 검토된 표시 계획 생성기이며 모든 writer에 적용되는 자동 줄바꿈 기능이 아니다.

수식 뒤 쉼표가 첫 행 높이에 남거나 별도 줄로 밀리면 기존 인접 쉼표가 정확히 하나임을
패키지에서 확인한 경우에만 마지막 수식 행으로 옮길 수 있다. 기존 텍스트 쉼표 제거와
수식 행 쉼표 삽입은 동일 변경으로 기록한다. 문장부호를 새로 만들거나 누락하지 않는다.
읽기 검사는 정확한 계획의 표시 스크립트만 역대응시키고, 쉼표 경계를 복원하여 전체
문단·미주 스냅샷을 원본 개정판과 비교한다. 수학적 동치 추정이나 모든 스크립트 차이 무시는 금지한다.

한글 저장·재열림에서 표시 스크립트와 개체 수·소유·순서·11pt 등 지정 서식을 확인하고,
영향 페이지를 실제 렌더하여 너비·기준선·문장부호·잘림을 검사한다. XML 기준선 값을
바꿨다는 이유로 성공으로 판정하지 않는다. 실제 한글에서 값이 되돌아가는 시도는 폐기 후보로
보존하고 반복하지 않는다. 미주에도 같은 개정판을 적용하고 복사·이동을 재검증한다.
단일 문항의 긴 등식 교정은 전체 교재의 밀도·쪽 배치·원본 검수 종료를 뜻하지 않는다.

합성 회귀: `tests/test_hwp_equation_line_layout.py`.

### 12.13 문장 안의 순수 그림과 그림 설명 묶음

문장 중간의 바둑돌·기호 그림 등을 설명 문자로 치환하거나 앞뒤 문장을 별도 문단으로
분리하지 않는다. 원본에서 검토한 순수 그림만 `type=figure, placement=inline`로
텍스트 `segments` 사이에 넣는다. `app/hwp_inline_figure.py`는 승인 사유·파일 SHA-256·
유효한 크기를 확인한 뒤 내장된 글자처럼 취급 그림을 삽입하고, 문단 모양 변경과
강제 문단 나눔 없이 다음 세그먼트로 이어간다. 본문·수식 스크린샷 대체에는 사용할 수 없다.

writer는 반환된 그림 증거를 실제 문서의 이미지 원장에 누락 없이 추가해야 한다.
원장이 없는 중첩 실행 경로는 조용히 삽입하지 말고 실패 처리한다. 신규 표·조건 상자 경로는
별도 연결·검증 전까지 지원된 것으로 간주하지 않는다. 블록 그림과 인라인 그림의 위치
선언이 실제 문맥과 다르면 `FIGURE_PLACEMENT_CONTEXT_MISMATCH`로 차단한다.
같은 모양의 소형 그림을 재사용하더라도 각각의 소유 문항·본문/해설·문장 순서와 occurrence ID를
분리한다. 동일 자산 해시가 반복된다는 사실만으로 원본의 모든 위치를 검수했다고 보지 않는다.

그림에 붙은 독립 계산식은 네이티브 수식으로 만들고, 순수 그림 crop에 계산식을 함께
흡수하지 않는다. 그림 설명 → 그림 → 계산 결과가 페이지 경계에서 떨어지면 해당 묶음에만
`keep_with_next`를 적용한다. 빈 줄 추가·본문 축소·그림 제거로 문제를 감추지 않는다.
실제 HWP/HWPX 재열림 후 문단 안 텍스트·그림 해시·수식의 전체 순서, 기준선과 단 경계,
묶음 배치를 검사한다. 미주 전후는 같은 내용 개정판이어야 하며 복사·이동도 다시 검증한다.
모의 객체 테스트는 COM·시각·출고 PASS가 아니다.

합성 회귀: `tests/test_hwp_inline_figure.py`.

### 12.14 조건 상자와 정렬 값의 실제 writer 계약

조건 상자는 의미 문단 목록인 `rows` 또는 검토된 `components` 중 하나만 사용한다.
일반 표의 `cells` 필드를 조건 상자에 넣으면 실제 writer가 읽지 않으므로
`AUTHORING_UNCONSUMED_CONTENT`로 COM 실행 전에 차단한다. 빈 내용은
`CONDITION_BOX_CONTENT_REQUIRED`, 두 표현의 동시 사용은
`AUTHORING_AMBIGUOUS_CONTENT`로 처리한다. 행 목록은 OCR 물리 행이 아니라
문장·조건 단위이며, writer가 하나의 네이티브 상자 안에 순서대로 넣는지 확인한다.

`align`은 한글 HAlign의 대소문자를 구분하는 정규 값으로 입력한다.
예를 들어 `Center`와 `center`를 같은 값으로 추정하지 않는다. 지원되지 않는 값은
`AUTHORING_ALIGN_INVALID`로 사전 차단하고 검토된 서식 개정판에서 명시적으로 수정한다.
정적 사전검사를 통과했다는 사실만으로 실제 COM 작성 성공을 추정하지 않는다.

실제 작성에서 새 계약 오류가 발견되면 실패한 시도와 정상 종료 증거를 보존한다.
본문·수식·원본 증거를 바꾸지 않는 스키마/서식 수정은 부모 manifest 해시와 변경 필드를
기록한 새 개정판에 한정한다. 재시도 전 작업 소유 PID 종료를 확인하고, 영향받은 역할만
직렬 재제작한 후 미주 전후의 전체 내용 및 저장 수식 순서를 다시 대조한다.
일반화된 회귀에는 합성 내용만 넣으며 실제 교재 전사는 Git에 포함하지 않는다.

합성 회귀: `tests/test_hwp_authoring_preflight.py`.

## 12.15 실행 지속과 COM 단계 기록 경합 처리

사용자의 작업 의도와 태스크 범위가 명확한 경우에는 확인 질문이나 계획만 남기고
멈추지 않고, 안전한 범위에서 구현·검증·기록까지 계속한다. 단, HWP COM은 문서
단위로 직렬 실행하며 기존 프로세스나 사용자 문서를 강제 종료하지 않는다.

COM 감독기가 `stage.json`을 읽는 동안 Windows의 원자적 교체(`os.replace`) 또는
백신·인덱서가 잠시 파일을 잡아 일시적인 `FileNotFoundError`, JSON 파싱 오류 또는
공유 위반을 일으킬 수 있다. 이 일시 경합을 작업 실패나 고아 HWP 세션으로 오인하지
않도록 감독기는 짧고 유한한 재시도 창을 둔다. 재시도 창 안에서 유효한 단계 기록을
읽으면 계속 진행하고, 창이 끝난 뒤에도 기록을 읽지 못하면 `STAGE_RECORD_UNREADABLE`
로 fail-closed 한다. 이 경우 산출물과 PID 증거를 보존하고 강제 종료하지 않으며,
소유된 HWP 창에 정상 종료를 요청한 뒤 새 직렬 세션을 별도 출력 경로에서 재개한다.

단계 기록 경합을 통과한 것만으로 COM 성공으로 보지 않으며, HWP/HWPX 재열림·수식 개체·미주
연결·300dpi 시각 검수와 원본 증거가 모두 닫히기 전에는 `PASS`나 `FINAL`로 승격하지
않는다.

## 12.16 원본 의미 블록 병합과 bounded pair 승격

OCR 물리 행을 그대로 문단으로 복사하지 않는다. 원본에서 하나의 조건 상자,
질문 문장 또는 보기 묶음으로 확인된 연속 행은 하나의 의미 블록으로 정규화하고,
그 블록 안의 `rows`·`segments`·수식 occurrence 순서를 보존한다. 반대로 서로 다른
문단·상자·문항의 행을 편의상 합치지 않는다. 병합에는 원본 페이지·bbox·입력 해시와
병합 전후의 의미 블록 ID를 기록한다.

긴 풀이 등식은 원본 occurrence 하나를 삭제하거나 평문으로 바꾸지 않고, 검토된
`pile`/등식 줄 표시 계획으로 배치할 수 있다. 표시용 줄 나눔은 원본 dialect·MathIR·
occurrence ID를 유지해야 하며, 새로운 수학 문장·라벨·정답을 추측해 삽입하지 않는다.
문장 안 인라인 수식은 같은 문단의 `segments`에 남겨 문장을 임의로 두 문장으로
절단하지 않는다. 조건 상자의 후속 행, 쉼표·마침표·연결어의 위치도 원본 대조로
닫아야 한다.

특정 문항 쌍의 600/900dpi crop, HWP/HWPX·COM 재열림, 300dpi 렌더, 네이티브
미주 복사·이동이 모두 닫힌 경우에도 그것은 `BOUNDED_CANDIDATE_QA_PASS`일 뿐이다.
전체 책의 source coverage와 출고 게이트가 닫히기 전에는 pair 결과를 `FINAL`로
승격하지 않는다. bounded report에는 남은 occurrence 수와 미해결 source/layout
근사(있는 경우)를 명시한다.

합성 회귀: `tests/test_source_block_contract.py`.

## 12.16.1 사용자 의도 실행과 긴 풀이식의 공통 출고 계약

이 절은 앞으로 요청되는 모든 PDF→HWP/HWPX·네이티브 미주 작업에 공통으로
적용한다. 사용자가 “할 수 있나”, “원해”, “도와줘”라고 표현하거나 변환·수정·
반영·완료를 요청하면, 범위가 안전하게 확정된 즉시 읽기→구현→검증→기록→출고를
계속 수행한다. 계획·능력 확인만 남기고 중단하지 않는다. 다만 원문 근거가 없는
추측, 파괴적 조작, 승인창 우회, 검증 전 `PASS`/`FINAL` 승격은 금지한다.

긴 풀이식은 다음의 단일 계약으로 처리한다.

1. 원본 수식 문자열·source hash·MathIR·occurrence ID를 정본으로 보존한다.
2. 600/900dpi crop에서 확인한 등식 경계에 한해 writer용 `pile`/`eqalign` 또는
   명시적 분수·괄호·위아래첨자 grouping을 추가할 수 있다. 이것은 표시 레이아웃만
   바꾸는 것이며 원본 수학 토큰·순서·소유 문항을 바꾸지 않는다.
3. 설명 문장이 수식 OCR 덩어리에 섞여 있으면, 수식 안에 넣지 않고 원본 읽기 순서의
   일반 editable text block으로 분리한다. 분리 사실·원문 hash·새 text block ID를
   manifest에 기록한다. 한국어 prose가 native equation script에 남으면 자동 FAIL이다.
4. writer script는 HWP 수식 문법 검사를 통과해야 하며, 저장 HWPX와 HWP COM
   재열림의 수식 순서·개수·baseUnit을 대조한다. 긴 식은 300dpi 전 페이지 렌더에서
   오른쪽 잘림·겹침·고아 줄이 없어야 한다.
5. 이 계약을 닫은 pair도 `BOUNDED_CANDIDATE_QA_PASS`이며, 전체 source coverage,
   미주 복사/이동, 전 페이지 시각검사와 book release gate가 닫히기 전에는 FINAL이 아니다.

구현 보조 함수는 `app.hwp_equation_line_layout.prepare_reviewed_display_layout`을
사용하며, 관련 합성 회귀는 `tests/test_hwp_equation_line_layout.py`에 둔다.

## 12.17 source-order figure와 solution page-boundary 계약

원본에 도형·그림·선택지가 함께 있는 경우 `SourceItemIR`의 블록 순서는 PDF의
읽기 순서를 그대로 보존한다. 순수 그림 crop을 허용하더라도 그림을 선택지 위나
아래로 임의 이동하지 않으며, 그림 블록의 `source_page`, bbox, SHA-256,
`actual_viewed` 증거를 남긴다. 그림 안의 글자·라벨을 별도의 수식이나 선택지로
중복 전사하지 않는다. 도형을 표나 편집 가능한 라벨 표로 대체한 경우에는 원본
충실도가 닫히지 않은 것으로 처리한다.

정답·풀이 문서는 문항별 원본 페이지 경계를 우선한다. 다음 문항이 원본의 새
페이지에서 시작하거나 직전 문항의 마지막 등식이 다음 페이지에 고아로 남는
경우에는 `solution_page_break_before: true` 같은 명시적 layout contract를
사용할 수 있다. 이 표시는 내용·수식·문항 ID를 변경하지 않으며, writer가
페이지를 보존했는지 COM 재열림과 300dpi 렌더에서 확인한다. 빈 공간을 만들기
위해 빈 줄을 반복 입력하거나 글자 크기를 임의로 축소해서는 안 된다.

이 계약은 문항 단위 bounded candidate에도 적용하지만, bounded QA PASS는 전체
책 FINAL이 아니다. 보고서에는 적용된 source-order/page-boundary 계약, 영향을 받은
페이지, 남은 whole-book gate를 함께 기록한다.

합성 회귀: `tests/test_source_block_contract.py`의 source-order 및
`solution_page_break_before` 계약 검사.

## 12.18 factorial-equality token guard

원본 수식에 팩토리얼 뒤 등호가 붙어 `3!=6`, `4! over 2!=12`처럼 보이는
경우에는 원본 문자열과 source hash를 그대로 보존하되, 한글 수식 writer에
넘기는 dialect는 `3! = 6`, `4! over 2! = 12`처럼 등호 앞뒤를 명시적으로
띄운다. 한글 수식 파서는 인접 토큰 `!=`를 `≠`로 해석하므로, 이를 그대로
저장·출력하는 것은 단순한 간격 차이가 아니라 원본 내용 오류이다.

컴파일러 정규화는 회귀 테스트로 고정하고, 저장된 HWP/HWPX와 COM 재열림
결과의 수식 script는 정규화된 dialect와 비교한다. 이때 `source_script`와
source hash는 변경하지 않으며, 원본 문자열과 출력 dialect의 차이를 원장에
명시한다.

## 12.19 grouped OCR block decomposition

OCR이나 PDF 텍스트 추출이 한 source block 안에 **여러 인쇄 수식과 설명
문장**을 합쳐 놓았더라도, 그 문자열을 하나의 거대한 native equation으로
writer에 전달하지 않는다. 600/900dpi 원본 crop에서 확인한 읽기 순서대로
`text → equation → text → equation` 같은 typed components로 분해하고, 각
인쇄 수식에 독립적인 `formula_occurrence_id`, MathIR, crop bbox와 SHA-256을
부여한다. 분해는 문구·숫자·부호를 생략하거나 새로 쓰는 작업이 아니며, 원본
문장은 editable text, 수식은 native equation으로 각각 보존하는 레이아웃
복원이다.

분해 후에는 source block 수와 formula occurrence 수를 별도로 집계한다.
한 덩어리로 저장했던 구형 원장과 새 occurrence 원장의 차이를 보고서에
기록하고, writer 입력·HWPX equation count·COM 재열림 순서가 새 원장과
일치할 때만 bounded QA PASS를 부여한다. 한 native equation에 긴 설명을
넣어 페이지 오른쪽이 잘리는 경우는 자동 FAIL이며, 글자 축소나 빈 줄 반복으로
우회하지 않는다.

### 12.20 통합본의 문제 본문 선행·문서 끝 미주 배치 계약

네이티브 미주 통합본의 목적은 문제를 복사하거나 이동할 때 해당 정답·해설
연결을 함께 보존하는 것이다. 따라서 **모든 과목과 모든 문항 범위**에 다음
배치 계약을 적용한다.

1. 통합본의 주 본문은 원본 읽기 순서의 문제만 `1번 → 2번 → … → 마지막
   문항` 순서로 배치한다. 문제 문서가 사용하는 인쇄 번호(예: `01`, `6-1`)와
   변형 문항 ID는 원본 그대로 보존하되, 정답·풀이 문단·해설 제목·해설
   그림을 주 본문에 삽입하지 않는다.
2. 각 문제에는 해당 문항의 **실제 native endnote reference를 정확히 하나**
   연결한다. `※`, `[해설]`, 일반 각주 문자, 숨은 텍스트, 복사된 해설 문장을
   참조 표식으로 대체하지 않는다. 문제 본문과 미주 연결의 occurrence ID,
   문항 ID, 인쇄 번호, 순서를 manifest에 기록한다.
3. 각 native endnote body에는 그 문항의 정답 및 해설만 원문 순서대로 둔다.
   다른 문항의 해설, 중복 문제 본문, 페이지 전체 캡처, 임의로 만든 풀이를
   섞지 않는다. 미주 body 순서는 문제 reference 순서와 1:1로 일치해야 한다.
4. HWPX의 저장된 모든 `hp:endNotePr`에는
   `hp:placement/@place="END_OF_DOCUMENT"`를 명시한다. `footNotePr`의
   기본값 `EACH_COLUMN`은 별개의 각주 설정이므로 미주 배치의 근거로 사용하지
   않는다. `endNotePr`가 없거나 `place`가 비어 있거나
   `EACH_COLUMN`·`EACH_PAGE` 등 다른 값이면
   `ENDNOTE_PLACEMENT_UNDECLARED` 또는 `ENDNOTE_PLACEMENT_INVALID`로
   자동 FAIL한다.
5. 출력 전 QA는 다음 세 가지를 모두 확인한다.
   - 주 본문에 문제 외 해설 제목·정답/풀이 블록이 누출되지 않았는지
   - 저장 HWPX의 native endnote 개수·문항 순서·body 내용이 manifest와
     일치하는지
   - 한글 재열림·렌더 후 마지막 문제 페이지 **바로 다음 새 페이지**에 첫 미주
     heading/body가 시작하는지. 마지막 문제 페이지 하단에 첫 미주가 보이거나,
     중간 빈 페이지 뒤에 첫 미주가 시작하면 `ENDNOTE_PAGE_BOUNDARY_NOT_FRESH_PAGE`로
     자동 FAIL한다. `END_OF_DOCUMENT` XML 선언만으로 이 물리적 경계를 통과로
     인정하지 않는다.
   - 그 이후 미주 영역만 이어지고, 문제와 미주가 페이지/단 중간에서 서로
     interleave되지 않는지
6. 실제 한글에서 문제 하나를 복사·이동하여 native 미주 연결이 유지되는지
   별도로 시험한다. 평문 표식이 따라오는 것만으로는 통과로 보지 않는다.
   복사 시험은 native 미주 수가 정확히 1개 늘고 **선택 문항의 미주 body**가
   정확히 1회 더 존재하는지, 이동 시험은 미주 body의 multiset·수식 수가
   보존되는지, 두 시험 모두 자동 번호·`END_OF_DOCUMENT` placement·원본
   HWP/HWPX hash·저장 HWP 재열림을 확인한다. 한 문항 복사에 문서 전체 수식
   수가 두 배여야 한다고 검사해서는 안 된다. 기본 도구는
   `tools/hwp_native_endnote_transfer_probe.py`이며, 이 시험은 확인한 문항
   범위의 editor-behaviour 근거일 뿐 전체 원문 충실도 PASS가 아니다.
   COM 선택 범위는 `Ctrl.GetAnchorPos(0)`을 그대로 신뢰하지 않는다. 일부
   한글 버전에서는 이 위치가 미주 `subList` 안으로 해석되므로, 주 본문
   top-level 문단을 순회하여 선택 HWPML2X에 정확히 하나의 `hp:endNote`가
   포함되는 문단을 찾고, 선택 문단의 미주 밖 텍스트·수식과 native reference
   count를 별도로 기록한다. 선택에 native reference가 0개이거나 2개 이상이면
   body·수식 delta가 맞더라도 `selected_native_endnote_reference=false`로
   FAIL 처리한다.
   미주 전·후 파일은 동일한 문제 개정판과 동일한 수식·그림 occurrence에
   기반해야 한다.

이 계약은 통합본을 만들 때마다 과목별로 적용하며, 한 과목만 통과한 상태를
전체 과목 완료로 승격하지 않는다. placement·주 본문 누출·문항 순서 중 하나라도
미검증이면 결과물은 후보/REVIEW_REQUIRED로 유지하고 `FINAL` 또는 출고
PASS로 표시하지 않는다.

합성 회귀: `tests/test_endnote_qa_gate.py`의
`test_endnote_placement_must_be_document_end`,
`test_endnote_placement_must_be_explicit`,
`tests/test_hwp_first_native_endnote_page_break.py`의 fresh-page 경계 fixture.
실제 출고에서는 `tools/patch_hwp_first_native_endnote_page_break.py`로 기존 빈
terminal main-story 문단의 fresh-page 속성을 적용한 뒤, COM 저장/재열림과
`tools/audit_hwp_endnote_page_boundary.py` 렌더 검사를 같은 output hash에 연결한다.
새 출고에서는 `--boundary-review`로 독립 마지막 문제 끝/첫 미주 검수 기록과
두 페이지의 300dpi 이상 full-page render를 연결한다. 첫 미주 쪽−1 역산이나
짧은 heading 부분 문자열만의 구형 v1 PASS는 인정하지 않는다. 상세 schema와
출고 함수 연결은 v12 기본 지시서 §8을 따른다.

## 12.21 문항 블록 고정·수식 표시 줄바꿈·경계 마스크 증거

묶음 고정의 상한은 실제 가용 페이지/단 높이다. 아래 keepWithNext는 제목·보기·종속
수식 등의 검토된 묶음에만 적용한다. 긴 문항/풀이 전체가 가용 높이를 초과하면 원문
의미 경계에서 묶음을 분리하고 큰 공백/빈 쪽이 생기지 않는지 검수한다. 기본 절차 §5가
이 예외의 정본이며, 문항 전 문단에 무조건 동일 속성을 넣는 것으로 완료하지 않는다.

문항이 중첩 표 셀 또는 `subList`에 들어 있는 경우 `pageBreak` 속성만으로는 제목과
조건·보기·선지·독립 수식이 분리되지 않는다. writer는 원본 source reading order로
문항 블록을 수집하고 마지막 문단을 제외한 각 문단의 `paraPr`에
`breakSetting/@keepWithNext="1"`을 적용한다. 중첩 문단을 포함하되 미주 anchor가
있는 해설 경계는 다음 블록으로 넘기지 않는다. 보정은 새 `paraPr` ID를 발급하고
`paraProperties/@itemCnt`를 실제 개수로 갱신해야 하며, 본문·표 셀·수식·그림·미주
anchor의 before/after fingerprint가 일치해야 한다. `tools/auto_keep_with_next.py`
및 `tools/patch_hwp_keep_with_next_blocks.py`는 이 오프라인 보정을 수행하고,
실제 한글 저장·재열림과 영향 페이지 렌더가 뒤따르지 않으면 COM/visual PASS로
승격하지 않는다.

긴 native equation은 source occurrence·MathIR·원본 script를 유지한 표시 레이아웃
변경으로만 줄바꿈한다. 허용된 경계는 최상위 세미콜론·화살표·쉼표·독립 등호·더하기
등이며, `<=`, `>=`, `!=`, 음수 부호, 괄호 내부 등호는 보호한다. `#` 또는
`eqalign` 삽입 전후에 token count/order, source hash, formula occurrence ID,
HWPX equation count와 COM readback count를 1:1 비교한다. 영향 페이지에서 식의
오른쪽 잘림·겹침·고아 행·문장부호 고립이 발견되면 `VISUAL_EQUATION_WRAP_FAIL`로
처리하고 출고를 중지한다. `tools/wrap_hwp_equation_scripts.py`의 안전 토큰 검사와
합성 회귀를 필수로 한다.

300dpi 이상 raster boundary QA는 원시 결과와 검토 결과를 분리한다. 중앙 단 구분선
또는 페이지 프레임이 안전 영역을 침범하는 것이 원본에서 확인된 경우에만 명시적인
`ignore_mask`를 사용할 수 있다. 마스크 파일의 절대경로·크기·SHA-256·적용 페이지·
근거 이미지를 evidence에 남기며, 마스크는 문자·표·수식 spill을 가릴 수 없다. 같은
페이지를 mask 없이 먼저 실행해 raw finding을 보존하고, mask 적용 후에도 내용 잉크가
경계 밖이면 FAIL이다. 전 페이지가 이 절차를 통과하고 수동 시각검토까지 닫힌 경우에만
`visual_pass=true`를 부여한다. 합성 회귀는
`tests/test_hwp_keep_with_next_blocks.py`, `tests/test_wrap_hwp_equation_scripts.py`,
`tests/test_raster_boundary_batch_qa.py`에 둔다.
