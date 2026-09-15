# Native 교사 서식 실행 계약

[진입 문서](TEACHER_NATIVE_WORKFLOW.md)와 같이 읽는다. 실행 config는 로컬에
두며 실제 교재 경로·문항 ID·이미지 해시는 공개 예제에 넣지 않는다.

## build: teacher-native-reflow/v1

| 필드 | 의미 / 검증 |
|---|---|
| schema, mode | schema 고정, 현재 adapter는 template_only만 지원. append 명시 오류 |
| source | 원본 path + sha256. 원시 HWP를 이 단계에서 다시 쓰지 않음 |
| native_candidate | 검수·서식 적용된 native staging HWPX의 path + sha256 |
| inventory | JSON path + sha256. items[].id가 중복 없는 원본 고유 ID |
| style_reference | 실제 기준 HWPX path + sha256. 수용/내용 원본과 구분 |
| candidate_item_ids | native anchor 순서와 1:1인 ID 배열 |
| selected_item_ids | 원본 순서의 중복 없는 부분집합 또는 전체 |
| roles | 아래 의미 해시. 숫자 refList ID를 config 의미로 사용하지 않음 |
| header | source_sha256, allowed_asset_sha256s; 이미지 속 텍스트는 별도 시각 검수 |
| layout | reserved_right_gap_hwpunit, column_height_hwpunit; 캐시 기반 계획일 뿐 실제 공간 PASS 아님 |
| output | 새 출력 경로. 기존 파일이면 거부 |

roles 필수 값은 workspace_para_sha256, body_para_sha256, body_char_sha256,
heading_para_sha256s, heading_text_sha256s이다. 마지막 값은 실제 본문과 다른
문서 제목을 식별하는 직접 텍스트 SHA-256이며 paraPr만으로 제목을 추정하지 않는다.
다른 역할의 native 서식은 staging 것을 보존한다. **기준본 hash를 넣는 것만으로
staging의 모든 표·보기·미주 서식이 그 기준과 같다고 판정하지 않는다.**
다른 기준을 처음 import하는 adapter는 모든 역할 매핑 및 ID 충돌 검증이 별도로 필요하다.

선택 필드 note_exclusions[]는 item_id, paragraph_index, payload_sha256,
reason, evidence(path+sha256)를 요구한다. 삭제 후보 문단 자체의 native payload와
원본 경계 근거가 일치해야 한다. source inventory에도 그 영역이 다음 context임을
기록한다. 내용이 모호하면 삭제하지 말고 review로 남긴다.
join_generated_note_label은 생성된 정답 표제만 첫 풀이 문단에 결합하며 원문
풀이 두 문단을 합치지 않는다. 그림-first 표제 분리를 해결했다고 보장하지 않는다.

## profile: teacher-style-profile/v1

reference_sha256와 profile_sha256로 버전 고정한다. catalogs는 charPr/paraPr/
borderFill/tabPr/numbering/bullet/style의 의미 해시와 참조 해석값이다.
sections는 secPr/colPr/endNotePr/header/footer, masterpages는 자산 hash와 실제
구조·기하, object_styles는 표·셀·수식 속성과 소유 위치다. usage는 각 문단의
native_path, 언어별 글자 참조, 표/미주/머리말 등의 컨테이너를 기록한다.
역할 후보는 실제 기준본에서 확인하여 역할 매핑으로 확정한다. 이 프로필 전체는
본문을 포함할 수 있으므로 **로컬 전용**이다. 공개할 때는 일반 수치만 별도로 추린다.

## release: teacher-release/v1

targets.hwp, targets.hwpx 각각 path+sha256, scope_ids, evidence를 받는다.
evidence는 source_scope/source_payload/style_roles/font_render/header_render/
workspace/endnote_order/com_roundtrip/whole_question_transfer/visual_qa의
정확한 10개 path+sha256 참조다.

각 증거의 schema는 teacher-evidence/v1. kind/target_sha256/scope_ids/비어 있지
않은 boolean checks/status/open_items/observations(method+artifact hash)가 필수다.
추가 요구:

- endnote_order.boundary: 마지막 본문과 첫 미주의 각각의 측정 방법·양의 물리 쪽.
  한쪽이라도 제목 역산이면 거부한다. first=last+1이어야 한다.
- font_render: coverage=all_applicable_roles, required_roles, role_renders[].
  각 역할의 예상/실제 폰트 배열, font_match, 해당 쪽과 렌더 artifact 해시.
  글꼴 이름 한 번 발견으로 전체 역할을 채우면 안 된다.
- whole_question_transfer.transfers[]: id/operation/whole_question/readback/
  payload_equal/readback_artifact/전후 payload hash. 실제 move 행도 필요.
- visual_qa: physical_page_count/automated_pages/human_reviewed_pages.
  자동 렌더 생성·자동 분석·사람이 본 범위는 원장에서 구분하고 과장하지 않는다.

이 gate는 관찰 근거의 필수 구조와 해시 연결을 검사한다. 허위로 작성된 관찰을
진실로 바꿔 주는 도구가 아니며, producer/reviewer는 실제 원본·렌더 검증을 해야 한다.
한 분야라도 OPEN이면 FINAL=false다. 패키지 합성검사 PASS와 교재 출고 PASS는 별개다.
