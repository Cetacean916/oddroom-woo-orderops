# OFFSET OrderOps · macOS universal app-entry

## 다운로드와 설치 위치

같은 GitHub Release에서 `pf07-macos-universal-1.0.7.zip`과
`SHA256SUMS.txt`를 받고, 압축을 풀기 전에 다음 결과를 해당 줄과
비교합니다.

```sh
shasum -a 256 pf07-macos-universal-1.0.7.zip
```

파일명이나 SHA-256이 다르면 실행하지 말고 다시 받습니다. 확인한 ZIP
전체를 새 전용 폴더에 풉니다. 원하면 패키지 전체 폴더를 Applications
아래에 둘 수 있지만 `PF07 Launcher.app`만 따로 이동하면 인접한 공통
런처와 payload를 찾을 수 없습니다. 실행을 시작한 뒤에는 패키지 폴더를
이동하거나 다른 버전 파일을 덮어쓰지 않습니다.

## 첫 실행

1. `PF07 Launcher.app`을 더블클릭합니다.
2. macOS가 다운로드 앱을 차단하면 Finder에서 앱을 Control-클릭 →
   `열기` → 다시 `열기`를 선택합니다. 이 무료 포트폴리오 산출물은
   unsigned / not notarized이며 유료 서명은 적용하지 않았습니다.
3. 런처가 Python 또는 컨테이너 런타임 누락을 표시하면 번호 순서의 공식
   링크를 엽니다. 0-KRW 유지 경로는 Moby 엔진을 선택한 Rancher
   Desktop입니다.
4. 설치·로그아웃·재시작 후 같은 앱을 다시 열면 패키지 내부 진행 상태를
   읽고 필수 구성요소를 재검사합니다.
5. `서비스 시작`을 누르고 Ready를 확인한 뒤 상점과 관리자를 엽니다.

기본 `DEMO_MODE`는 합성 주문만 사용하고 실제 결제·이메일·HubSpot·Slack을
호출하지 않습니다. `CONNECTED_MODE`는 실제 Slack 설정 메시지와
HubSpot·Slack 외부 효과를 만들 수 있으므로 공통 안내를 먼저 읽고 보호된
토큰 파일과 정확한 대상 ID를 준비한 경우에만 사용합니다.

## 다시 실행, 종료, 업데이트

허브에서 언어, 모드, 시작, 상점, 관리자, 중지, 복구, 백업·복원, 통제된
업데이트, 옵션 HTTPS 터널, 증거 내보내기를 사용합니다. 터미널 대체
경로는 `pf07.command`와 다음 CLI입니다.

```sh
./pf07 status
./pf07 stop
./pf07 start
./pf07 recover
```

`stop`은 서비스를 중지하지만 주문·설정과 패키지 소유 볼륨을 보존합니다.
나중에 같은 폴더의 앱을 열면 같은 상태로 다시 시작할 수 있습니다.
업데이트는 기존 추출본 위에 새 ZIP을 덮어쓰지 않고, 새 버전을 별도
폴더에 푼 뒤 새 허브에서 지원되는 정확한 이전 추출 폴더를 선택합니다.

백업·복원·제거·외부 연결·옵션 HTTPS 터널의 정확한 명령과 데이터 영향은
[`packaging/common/PACKAGE-README.ko.md`](packaging/common/PACKAGE-README.ko.md)를
참조합니다.

Apple Silicon과 Intel은 동일한 POSIX 앱 어댑터와 Python 런처 코어를
사용합니다. 이 산출물은 `.app` 구조·권한·아키텍처 선언·공통
코어·아카이브 경계를 검증했으며 실제 Mac 컨테이너 스택 또는 Safari
실행을 주장하지 않습니다.
