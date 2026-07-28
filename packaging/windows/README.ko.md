# OFFSET OrderOps · Windows x64

## 다운로드와 설치 위치

같은 GitHub Release에서 `pf07-windows-x64-1.0.8.zip`과
`SHA256SUMS.txt`를 받습니다. ZIP을 풀기 전에 PowerShell에서 다음 값을
확인하고 `SHA256SUMS.txt`의 해당 줄과 비교합니다.

```powershell
Get-FileHash .\pf07-windows-x64-1.0.8.zip -Algorithm SHA256
```

파일명이나 SHA-256이 다르면 실행하지 말고 다시 받습니다. 확인한 ZIP
전체를 임시 폴더가 아닌 새 전용 폴더에 풉니다. 공백·한글 경로도
지원합니다. 실행을 시작한 뒤에는 패키지 폴더를 이동하거나 다른 버전
파일을 덮어쓰지 않습니다.

## 첫 실행

1. `PF07-Launcher.exe`를 더블클릭합니다.
2. 허브가 필수 구성요소를 확인합니다. 누락 시 번호 순서와 공식 설치
   링크를 따르고, 설치나 재부팅 후 같은 런처를 다시 엽니다.
3. `서비스 시작`을 누르고 서비스 5개가 모두 Ready가 될 때까지
   기다립니다.
4. `상점 열기` 또는 `관리자 열기`를 사용합니다. 관리자는 로그인이
   필요하며 `주문 관리 계정 보기`에서 패키지 로컬 계정을 확인합니다.

기본 0-KRW 컨테이너 경로는 Moby 엔진을 사용하는 Rancher Desktop입니다. Docker Desktop은 수신자가 현재 약관상 적용 가능성을 직접 확인한 경우에만 선택 가능한 대안입니다. Python 3.10 이상도 필요합니다. 첫 설치와 컨테이너 이미지 취득에는 인터넷 연결이 필요합니다.

기본 `DEMO_MODE`는 합성 주문만 사용하고 실제 결제·이메일·HubSpot·Slack을
호출하지 않습니다. `CONNECTED_MODE`는 실제 Slack 설정 메시지와
HubSpot·Slack 외부 효과를 만들 수 있으므로 공통 안내를 먼저 읽고 보호된
토큰 파일과 정확한 대상 ID를 준비한 경우에만 사용합니다.

## 다시 실행, 종료, 업데이트

명령 대체 경로는 `START-PF07.cmd`와 `pf07.cmd`입니다.

```bat
pf07.cmd status
pf07.cmd stop
pf07.cmd start
pf07.cmd restart
pf07.cmd recover
pf07.cmd diagnostics
pf07.cmd evidence-export
```

`stop`은 서비스를 중지하지만 주문·설정과 패키지 소유 볼륨을 보존합니다.
나중에 같은 폴더의 런처를 열면 같은 상태로 다시 시작할 수 있습니다.
데이터까지 제거하려면 먼저 암호화 백업을 만든 뒤 확인 문구가 필요한 제거
기능을 사용합니다.

업데이트는 기존 폴더 위에 새 ZIP을 덮어쓰는 방식이 아닙니다. 검토된 새
버전을 별도 폴더에 풀고 새 허브의 통제된 업데이트에서 지원되는 정확한
이전 추출 폴더를 선택합니다. 백업·복원·제거·외부 연결·옵션 HTTPS
터널의 정확한 명령과 데이터 영향은
[`packaging/common/PACKAGE-README.ko.md`](packaging/common/PACKAGE-README.ko.md)를
참조합니다.

## 선택 사항: Windows KVM 테스트 키트

같은 Release의 `pf07-windows-kvm-test-kit-1.0.8.zip`은 이 실행
패키지를 Windows에서 검수하기 위한 별도 보조 키트이며 실행본이 아닙니다.
빠른 CMD 사전검사는 파일명·SHA·압축 해제·런처 버전만 확인합니다. 실제
상점·관리자·중지·복구까지 확인하려면 테스트 키트의 `README.ko.md`와
`PF07-KVM-TEST.html`에 적힌 전체 수동 절차를 수행해야 합니다.

이 Windows 산출물은 Linux 호스트에서 PE·스크립트·아카이브·공통 코어 계약을 검증한 패키지입니다. 실제 owner KVM 전체 스택/브라우저 실행 결과를 주장하지 않습니다.
