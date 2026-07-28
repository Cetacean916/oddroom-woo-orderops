# PF07 Windows KVM owner test kit

이 키트는 `pf07-windows-x64-1.0.8.zip`을 Windows 환경에서 검수하기 위한
보조 도구입니다. PF07 실행 패키지를 대신하지 않습니다.

## 준비물

- 같은 GitHub Release에서 받은 `pf07-windows-x64-1.0.8.zip`
- 이 테스트 키트의 압축을 푼 폴더
- Windows x64 가상머신 또는 별도 Windows 시험 장비
- 전체 런타임 검수 시 Rancher Desktop(Moby 엔진), Python 3.10 이상,
  첫 설치용 인터넷 연결

구매자 ZIP은 먼저 풀지 말고 원본 ZIP 상태로 보관합니다. 테스트 키트의
`buyer-package-binding.json`이 파일명과 SHA-256의 기준입니다.

## 1. 빠른 사전검사

1. `RUN-KVM-TEST.cmd`를 더블클릭합니다.
2. 파일 선택창에서 원본 `pf07-windows-x64-1.0.8.zip`을 선택합니다.
3. 완료 안내창에서 Archive name, Archive hash, Launcher found가 모두
   `True`인지 확인합니다.
4. 바탕화면의 `PF07-WINDOWS-KVM-PREFLIGHT.json`을 열어 아래 사전검사
   PASS 조건을 모두 확인한 뒤 보관합니다.

사전검사 PASS 조건:

```json
{
  "archive_name_pass": true,
  "archive_hash_pass": true,
  "unicode_space_extraction_pass": true,
  "launcher_present": true,
  "launcher_version": "1.0.8",
  "actual_full_stack_executed": false
}
```

`actual_full_stack_executed: false`는 사전검사에서는 정상입니다. 이 CMD는
파일명·SHA-256, 한글/공백 경로 압축 해제, 런처 존재, PE 제품 버전만
검사합니다. PF07 런타임, 상점, 관리자, 종료, 복구는 실행하지 않습니다.

## 2. 전체 Windows 실행 검수

1. `PF07-KVM-TEST.html`을 더블클릭합니다.
2. 상단에서 같은 구매자 ZIP을 선택하고 `Result: PASS`를 확인합니다.
3. 구매자 ZIP 전체를 한글과 공백이 포함된 새 폴더에 직접 풉니다.
4. `PF07-Launcher.exe`를 실행하고 그래픽 안내에 따라 필수 구성요소를
   준비합니다. 설치나 재부팅 후 런처를 다시 엽니다.
5. `서비스 시작`을 선택하고 서비스 5개가 모두 Ready가 될 때까지
   기다립니다.
6. 허브에서 상점과 관리자를 열고 관리자가 로그인을 요구하는지
   확인합니다. 상점에서 합성 주문 1건을 완료하고 주문 관리에서 같은
   주문을 확인합니다.
7. `상세 상태 보기`에서 `compose_project`를 기록합니다. 한국어 → 영어
   → 한국어로 전환한 뒤 다시 상세 상태를 열어 같은
   `compose_project`, 서비스 5개 Ready, 앞서 만든 주문이 유지되는지
   확인합니다.
8. 허브에서 서비스를 중지한 뒤 다시 시작하고, 같은 주문과 설정이
   돌아오는지 확인합니다.
9. Rancher Desktop의 그래픽 Containers 화면에서 현재 PF07 Compose
   프로젝트의 `n8n` 컨테이너 하나를 중지합니다. 허브의 `서비스 다시
   시작` 또는 `문제 복구`를 사용해 서비스 5개가 다시 Ready가 되는지
   확인합니다.
10. `상세 상태 보기`를 열고 `상태 자료 ZIP 저장`을 실행한 뒤, 생성된
    redacted ZIP을 실행 패키지 밖에 보관합니다.
11. HTML의 10개 체크박스를 실제 완료한 항목에만 표시하고
    `Download machine-readable result`를 선택합니다.

## 3. 최종 확인

전체 Windows 검수 완료를 주장하려면 다음 자료가 모두 필요합니다.

- `PF07-WINDOWS-KVM-PREFLIGHT.json`의 사전검사 PASS 항목
- 상단 ZIP 검증 결과의 `PASS`
- `archive_binding_pass: true`
- `PF07-WINDOWS-KVM-RESULT.json`에서 10개 `steps` 값이 모두 `true`
- `all_steps_checked: true`
- `owner_kvm_execution: true`
- `completion_state: "OWNER_REPORTED_COMPLETE"`
- 실제 합성 주문·관리자 로그인·언어 전환·중지·재시작·복구의 직접 확인
- 실행 패키지 밖에 보존한 redacted 상태 자료 ZIP

체크박스와 `owner_kvm_execution`은 실제 수행 사실을 기록하는 항목입니다.
HTML은 정확한 ZIP과 10개 체크를 빠뜨린 결과를 `INCOMPLETE`로 기록하지만,
체크한 행동이 실제로 수행됐는지 자동 판정하거나 증명하지는 않습니다.
실제로 수행하지 않은 항목은 체크하지 마십시오.
