# HWP COM 자동화 파일 접근 승인 보안 기준

이 문서는 PDF→편집형 HWP/HWPX 및 네이티브 미주 변환에서 한글 COM의 파일
접근 승인 팝업을 무인 처리하기 위한 공통 보안 기준이다. 문서·작업 원본과
파생 산출물은 승인된 로컬 작업 폴더 안에서만 다룬다.

## 기준 설정

- 한글 COM 모듈: `FilePathCheckDLL`
- 레지스트리: `HKCU\Software\HNC\HwpAutomation\Modules`
- 값 이름: `FilePathCheckerModule`
- 값 형식: `REG_SZ`
- 현재 검증 DLL: 프로젝트에 번들된 `pyhwpx\FilePathCheckerModule.dll`
- 현재 검증 SHA-256: `9AC5B97C47AC8AED1E8BCA27A3EEF39411361D8F68C262509F0C40A8F9D21BB6`
- 한글 2024와 DLL: 모두 x86 / PE32

동일 SHA-256의 `FilePathCheckerModuleExample.dll`은 pyhwpx가 안내하는
한컴 개발자센터 Automation 보안 모듈 배포본과 동일한 바이트로 확인한다.
출처가 확인되지 않은 DLL을 내려받거나 자동 설치하지 않는다.

## 필수 실행 순서

1. `resolve_registration()`이 레지스트리 값, 파일 존재, `REG_SZ`, SHA-256,
   DLL PE 형식, 한글 실행 파일의 비트수를 확인한다.
2. `create_secure_hwp()`가 `Hwp(..., register_module=False)`로 새 COM
   인스턴스를 만든다.
3. 파일 `Open`, `SaveAs`, `Print`, 그림 삽입 또는 미주 삽입 전에
   `HwpObject.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")`를
   직접 호출하고 실제 반환값을 확인한다.
4. 반환값이 `False`이거나 모듈·비트수·레지스트리 검증이 실패하면
   `HWP_SECURITY_MODULE_NOT_ACTIVE`로 즉시 실패한다. 승인 팝업을 기다리거나
   좌표 클릭으로 우회하지 않는다.

공통 헬퍼는 `app/integrations/hwp_security.py`의
`create_secure_hwp`, `activate_registered_module`, `security_snapshot`이다.
Writer, native-endnote, readback, transfer probe는 이 헬퍼를 사용해야 한다.

## 검증 규칙

- HWP COM은 병렬로 실행하지 않고 직렬로 실행한다.
- 테스트는 기존 `outputs`를 덮어쓰지 않는 새 `work/hwp_security_probe_*`
  폴더에 저장한다.
- 서로 다른 두 문서를 새 파일명으로 저장하고 HWP/HWPX를 다시 열며 PDF도
  출력한다.
- 승인 팝업 0회, 새로 만든 Hwp PID의 정상 종료, 세 형식 파일 생성이 모두
  확인되어야 보안 테스트 PASS다.
- 이미 실행 중인 출처 불명 Hwp.exe를 이름으로 강제 종료하지 않는다.
- `PYHWPX_FORCE_STANDALONE=1`은 다수의 기존 Hwp 프로세스로 DispatchEx가
  makepy에 걸릴 때만 직렬 테스트에 사용한다.

실행 예:

```powershell
python tools/hwp_com_security_serial_probe.py
```

검증 스크립트는 `report.json`에 DLL 경로·해시·비트수, 레지스트리 키,
RegisterModule 경로, 테스트 파일, 팝업 목록, 새 COM PID 종료 결과를 남긴다.

## 실패 처리

보안 모듈이 없거나 등록 값이 틀리면 `HWP_SECURITY_MODULE_NOT_ACTIVE`를
기록하고 HWP 파일을 열지 않는다. 등록이 유효한데 COM 생성이 일시적으로
실패하면 해당 직렬 세션만 bounded timeout으로 종료하고, 새 격리 세션에서
한 번 재시험한다. 반복되는 경우 원인·PID·레지스트리·DLL 정보를 보고하고
무기한 재시도하지 않는다.
