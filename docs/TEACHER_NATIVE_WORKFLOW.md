# Native HWP 교사 부교재 재사용 진입점

이 문서는 [v12 한 번 요청 정본](PDF_HWP_V12_ONE_REQUEST_WORK_INSTRUCTIONS.md)의
**이미 편집 가능한 HWP 분기**를 구체화한다. 기존 정본을 대체하거나 책별
성공 수치를 새 책의 PASS 상수로 만들지 않는다. 먼저 저장소 AGENTS.md,
[원문 충실도](PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md),
[COM 보안](HWP_COM_AUTOMATION_SECURITY.md),
[미주 순서](NATIVE_ENDNOTE_DOCUMENT_ORDER_POLICY.md),
[교사 배치 보정](HWP_TEACHER_LAYOUT_REPAIR_RELEASE.md)을 읽는다.

## 1. 두 모드와 지원 경계

- `template_only`: 기준본의 서식만 이용. 기준본 문항·미주·과목 이미지를
  새 원본 내용으로 간주하지 않는다.
- `append_to_teacher`: 교사의 기존 개념·문항·수식·표·그림·미주를 보존한
  사본에 추가. 기존 prefix의 내용·소유 개체 증명과 native 병합이 먼저 필요하다.

`tools/teacher_workflow.py build`는 **native_staged_reflow 어댑터**다.
검수된 native 전송 후보 + 고유 문항 원장 + 서식 역할 해시 + 올바른 원본 머리말
자산을 입력받아 새 범위/조판으로 재구성한다. 원시 HWP의 임의 문항 경계를
자동 인식하거나 서로 다른 refList를 무조건 합치는 범용 변환기가 아니다.
원시 HWP → native staging은 기존 native range/clipboard 절차를 사용하되
해당 원본용 SourceItemIR 어댑터를 먼저 확정한다. 새로운 다구역 형식/append는
전용 어댑터와 대표 시험이 없으면 명시적으로 차단한다. 이것을 OCR 우회나
전체 작업 중단으로 해석하지 말고, 해당 어댑터를 구현·검증하며 진행한다.

## 2. 입력 계약과 실행 순서

정확한 config/profile/evidence 필드는 [입력 계약](TEACHER_NATIVE_INPUT_CONTRACT.md)에 있다.

1. 원본·기준본·원장·native 후보·코드 해시와 dirty patch를 로컬에 보존.
   표지 개수/파일명 숫자가 아니라 과목·단원·회차·인쇄번호·변형을 ID로 연결.
   `context_prefix`, 다음 단원 교재정보 표, 독립 개념, 연속 본문을 별도 분류.
   특히 다음 단원 정보 표가 이전 solution 범위에 들어가는지 검사한다.
2. 프로필 추출: `python tools/teacher_workflow.py profile --input REFERENCE.hwpx --report profile.json`.
   프로필에는 언어군별 폰트 의존성, char/para/tab/numbering/style/border의
   해석값 및 해시, 지면/단/미주, 바탕쪽 자산, 모든 문단 사용 위치가 있다.
   HWPX의 0/4294967295 상속 sentinel은 실제 폰트/서식 ID와 구별한다.
3. SourceItemIR의 문제·answer·solution native 개체를 보존해 staging을 만든다.
   OCR/페이지 이미지/새로 타이핑한 수식은 기본 경로가 아니다. 모든 수식의
   소유·순서·script, hc:img 자산 바이트, 표 셀 주소/병합/내용을 검사한다.
4. `teacher-native-reflow/v1` config를 준비한다. 원본/source inventory/
   native_candidate/style_reference는 각각 path+SHA-256. 역할 ID는 직접
   사용하지 않고 프로필의 의미 해시로 찾는다. `candidate_item_ids`는 후보
   anchor와 1:1, `selected_item_ids`는 원본 순서의 부분집합/전체집합이어야 한다.
   머리말은 source hash와 허용 asset hash 목록/자르기 원본 근거에 연결한다.
5. `python tools/teacher_workflow.py build --input run.json --report build.json`.
   기존 출력 덮어쓰기는 거부한다. 결과는 `BUILT_REQUIRES_QA`, FINAL=false.
   다음 단원 정보 표 제외는 원본 경계·문항 ID·payload 해시·근거 파일 해시가
   있는 `note_exclusions`에만 허용. 생성한 정답 표제와 첫 풀이 문단의 결합은
   `join_generated_note_label` 명시 시에만 허용하고 원본 풀이 문단끼리 합치지 않는다.
6. 별도 폴더에서 대표 일반/긴 수식/표·조건/그림/보기/단원·회차 경계/마지막
   문항·첫 미주 시험. 문제 지면은 B4 약 3문항(좌1/우2), 복잡하면1–2문항.
   약60mm 실제 필기 공간을 마지막 가시 개체 끝부터 측정한다. 캐시된 높이와
   빈 엔터 수는 최종 증거가 아니다. PDF의 텍스트·수식·표·그림·도형 leaf object
   중 해당 문항의 마지막 endpoint에서 다음 문항 marker 또는 물리 단 끝까지를
   측정한다. 복합 텍스트 블록은 블록 bbox가 아니라 leaf endpoint를 사용하고,
   다음 문항의 native anchor 바로 앞 단원/회차 구조 제목은 앞 문항 endpoint로
   귀속하지 않는다. 이 제외는 heading object hash, anchor 위치, 같은 물리
   페이지·단 좌표를 함께 기록한 경우에만 허용하며 일반 본문·조건·표·그림을
   제목으로 일괄 제외해서는 안 된다.
   끝점이 불명확하거나 60mm 미만이면 `REVIEW_REQUIRED`다. 렌더 증거가 있는
   item별 page-break 재배치는 `question_page_break_before_item_ids`와 hash-bound
   `question_layout_exception_evidence`로만 허용한다. 긴 식을 일괄 축소하거나
   script를 변경하지 않는다. question anchor가 공유하는 `paraPr`에
   `breakSetting.pageBreakBefore`를 붙여 전역 스타일을 바꾸지 않는다. 이 방식은
   HWPX 내부에서는 정상처럼 보여도 한글 PDF 출력에서 뒤쪽 source-owned 문항을
   누락시킨 실패 이력이 있다. 빈 spacer paragraph의 page-break도 2단 한글 출력에서
   무시된 사례가 있으므로 기본 보정으로 쓰지 않는다. 검증된 보정은 **다음 문항의
   독립 native anchor에만** 명시 페이지 나눔 속성을 부여하는 방식이다. anchor가
   공유하는 스타일 객체는 복제·변경하지 않으며, 새 HWP/HWPX 재열림 PDF에서 **모든 native
   reference 1..N이 첫 native 미주 앞 main story에 존재하는지**를 먼저 확인한다.
7. `python tools/teacher_workflow_com.py --input pilot.hwpx --out NEW_DIR --lock SHARED_LOCK`.
   직렬 보안 세션, HWP/HWPX 저장/재열림, 실제 B4 출력. 모든 COM 호출은 외부
   단계 deadline 하에 실행한다. 고착 시 worker/HWP/lease를 보존하고 timeout으로
   반환한다. 이전 worker 종료·소유 PID 종료를 확인한 뒤 원인 수정 후 한 번 재시험.
   기존 사용자 HWP를 종료하지 않는다. 이 lease를 모든 동시 작업자가 공유해야 한다.
8. `--transfer 11 8 6 3 0`처럼 **현재 pilot의** zero-based 선택을 지정하면
   문항 전체를 새 문서에 역순 복사하고, 첫 문항을 끝으로 Cut/Paste하여 이동한다.
   이후 HWP 재열림 HWPX에서 각 문항·해설 payload를 다시 비교한다.
   이 숫자는 예시이지 다음 책의 고정 시험 범위가 아니다.

   Windows native clipboard는 `Hwp Native` 형식의 실제 바이트가 생성될 때만
   성공이다. sequence 변경이나 내부 Cut/Paste/HWPX readback 성공은 이를
   대체하지 않는다. 복사 뒤 10초 이내에 native format ID·사용 가능 여부·sequence·
   STA message pump 기록을 남기고, 실패하면 같은 세션을 반복하지 않는다. 저장·
   정상 종료 후 새 격리 세션에서 같은 범위를 **한 번만** 재시험한다. 재실패는
   `CLIPBOARD_NATIVE_UNAVAILABLE`로 기록하여 FINAL을 차단하되, 내부 Cut/Paste
   검증은 별도 evidence로 보존한다.

   전체 범위 검증은 `--transfer-all --item-ids-json SOURCE_AUDIT.json`으로 실행한다.
   `scope_ids`가 현재 target anchor 수와 정확히 같을 때만 허용하며, 각 source-owned
   ID마다 native Copy와 native Cut/Move를 한 번씩 수행한다. Copy 대상은 새 문서이고
   Move 대상은 의도적으로 역순인 별도 새 문서여야 한다. 두 readback HWPX에서
   문항·조건·보기·표·그림·수식·native 미주의 payload SHA-256을 source와 비교한다.
   이 과정에서 생긴 source/destination 탭은 저장 뒤 모두 `Close(isDirty=False)`로
   정상 닫고, 남은 소유 PID가 있으면 강제 종료하지 않은 채 `OWNED_PROCESS_DID_NOT_EXIT`
   로 차단한다.

   긴 범위에서 Windows clipboard가 특정 세션의 `OpenClipboard` 접근 거부로 중단되면
   같은 HWP 세션에서 계속 반복하지 않는다. 실패한 **동일 범위**는 저장·정상 종료 후
   새 격리 세션에서 한 번만 재시험한다. 그 재시험이 성공하고 나머지 범위가 정상이라면,
   남은 source-owned ID는 짧은 새 격리 세션 묶음으로 직렬 처리할 수 있다. 각 묶음은
   source hash, 실제 `Hwp Native` bytes, Copy/Move, payload readback, 보안 모듈,
   approval window 0개, owned PID 종료를 모두 보관한다. 이후
   `tools/teacher_transfer_merge.py`가 모든 묶음의 정확히 한 Copy+Move를 hash-bound
   원장으로 합친다. 실패한 묶음, 중복/누락 ID, ready가 아닌 native clipboard record,
   source hash 불일치, 남은 소유 PID는 합칠 수 없으며 FINAL을 차단한다.
9. 대표 통과 후 같은 경로로 전체 적용. 변경 영향만 재검증. 별도 문제/풀이/
   통합은 같은 content revision에서 생성한다. 사용자가 통합만 요청하면2개,
   기본은 전체3역할 HWP/HWPX6개. QA·문항별 파일은 출고 폴더 밖에 둔다.

## 3. 반드시 검사할 편집 계약

- B4 72852×103180 HWPUNIT, 좌우15mm/상하10mm/머리말25mm/꼬리말20mm,
  2단 같은 너비/간격 약8mm는 알려진 기준값이다. 새로 지정된 실제 기준본을 우선.
- 사각 지면 테두리는 pageBorderFill 참조만 교정한다. 공유 borderFill을 바꾸어
  조건·표 선을 지우지 않는다. 가운데 선과 본문 여유를 실제 B4 렌더로 확인한다.
- 본문 일반값 KoPubWorld돋움체 Medium11.5pt/장평100/자간-10/LEFT/160%.
  번호·머리말·기호는 역할별. native HYhwpEQ1100 기준, 축소 예외는 위치·크기·
  가독성·source script 해시가 필요하다. 설치명만 있거나 PDF에 한 번 등장했다고
  전체 역할 폰트 PASS 금지. 본문/문제번호/선택지/조건상자/표/정답/풀이/미주/
  머리말의 각 역할에 대해 HWPX charPr·paraPr → HWP COM readback → PDF span
  (실제 글꼴·크기·좌표·render hash) 연결이 있어야 한다. 대체는
  KOPUB_FONT_NOT_ACTIVE.
- 보기 3+2는 탭·개체 기하로 재현. 공백 반복 정렬 금지. 긴 보기/분수/표 예외 기록.
  3+2가 수식 폭을 줄이거나 겹치게 만드는 경우에는 같은 대상 HWP/HWPX/PDF 해시,
  실제 다섯 표식 좌표, compact 2+1+2 기하, 원인과 crop을 가진 명시적 예외만 허용한다.
  임의의 2+1+2 또는 과거 교재 예외를 새 자료에 적용하지 않는다.
- 제목과 본문이 같은 paraPr를 사용할 수 있다. **paraPr만으로 제목을 제거하지
  않는다.** 해시로 식별된 본문 외 블록만 제외한다. 복사 제목에서 secPr/머리말
  제어를 다시 복제하지 않는다. 중복 머리말 개체는 실제 HWP 열기 실패를 일으킬 수 있다.
- 원본 머리말 이미지의 과목명까지 확인. 기준본에서는 위치/배치만 재사용한다.
  raw source asset hash → deterministic crop/derivation → target masterpage asset
  → HWP/HWPX 재열림 asset → PDF top-band raster까지 연결한다. 이미지 내 과목명·
  위치·크기·여백이 실제 렌더에서 맞지 않으면 PASS하지 않는다.
  모든 문항 먼저 → 다음 새 물리 페이지부터 정답·전체 풀이 native 미주.
  마지막 본문 개체와 첫 note 개체 쪽을 각각 측정한다. 제목쪽-1 역산 금지.
- 생성 정답 표제의 고아 배치, 다음 단원 정보 표의 미주 혼입, 마지막 빈 쪽도 검사.

## 4. 증거와 판정

`tools/teacher_workflow.py gate`는 `teacher-release/v1` 입력의 필수 10분야
증거를 검증한다. 빠진 schema/key/파일/관찰, 빈 checks, stale target hash,
다른 scope, 움직임 미시험, 단일 폰트 존재검사, 비인접 미주 경계는 차단한다.
각 evidence는 `teacher-evidence/v1`, kind, target_sha256(HWP/HWPX), scope_ids,
명시적 boolean checks, status, open_items, hash-bound observations를 갖는다.
font_render는 required_roles와 일치하는 role_renders(실제/예상 폰트·쪽·렌더 해시),
transfer는 각 행의 readback_artifact와 전후 payload 해시를 요구한다.
visual_qa는 전 페이지 자동 검사 범위와 실제 본 대표 쪽을 별도로 요구한다.
필수 분야: source_scope/source_payload/style_roles/font_render/header_render/
workspace/endnote_order/com_roundtrip/whole_question_transfer/visual_qa.

이 집계기는 관찰을 창작하지 않는다. 자동 B4저해상도 픽셀 동등성, 전 페이지
300dpi 렌더, 자동 기하 QA, 사람이 본 페이지는 각각 별도 원장으로 기록한다.
한 분야의 검사 미완료를 다른 분야 PASS로 대신하지 않는다. 기존 책의 사용자
수용/FINAL 보고서와 이번 재사용 패키지 시험 판정은 별개다.

원본의 인쇄 문항번호는 단원마다 재시작할 수 있으므로, 그것을 PDF marker의 전역
순번으로 사용하지 않는다. source inventory는 고유 item ID와 원래 인쇄번호의
대응을 보존하고, 재조판 PDF의 marker 순서는 현재 target HWPX의 실제 native
endnote reference 1..N에서 읽는다. main story 끝은 제목 위치나 과거 페이지 상수가
아닌, 실제 PDF에서 처음 나타나는 paired `정답:`·`해설:` native-endnote label로
물리 측정한다. HWP/HWPX GUI PageCount와 각 B4 PDF PageCount가 다르면 그 차이를
COM evidence의 OPEN으로 남긴다.

## 5. 재사용 이력과 한계

[추적 원장](TEACHER_NATIVE_TRACEABILITY.md), [다음 책 요청문](TEACHER_NEXT_BOOK_PROMPT.md),
`tests/test_teacher_workflow.py`와 `tests/test_hwpx_teacher_release_repair.py`를 따른다.
실제 교재 파일/그림/문항·해설/개인대화/로컬 절대경로 config는 Git에 넣지 않는다.
개인 전역 스킬이나 모델 설정을 이 문서 설치 과정에서 바꾸지 않는다.
모델명은 품질 증거가 아니다. 이번 실행의 실제 확인 가능한 설정만 기록한다.
그림으로 시작하는 미주의 생성 정답 제목은 한글에서 단 경계에 고립될 수 있다.
keepWithNext/columnBreak 속성을 넣었다는 이유로 해결 판정하지 않는다.
`note_column_start_item_ids`는 실험용 후보 보정이며 실제 렌더 통과 증거가 없는
한 재사용 기본값으로 삼지 않는다. 알려진 미해결 배치는 visual_qa의 open_items로 남긴다.
# Representative endnote layout repair (2026-09-15)

The representative gate found that paragraph-only `keepWithNext`, `keepLines`,
`columnBreak`, and spacer adjustments do not reliably control a floating
explanation figure after HWP COM round-trip. They must not be recorded as a
PASS merely because the XML contains those flags. For a confirmed item-level
repair, the bounded adapter may move the first native explanation picture into
the first explanation paragraph/run (`note_image_before_label_item_ids`) while
preserving the source payload and native endnote relationship. The repair is
valid only after serial HWP/HWPX save-close-reopen, physical B4 rendering, and
manual inspection of the affected page. This is an item-scoped exception, not
a global reorder rule; if the rendered title/figure relationship is not
verified, the gate remains BLOCKED.
