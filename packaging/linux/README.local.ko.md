# OFFSET OrderOps · Linux local

## 다운로드와 설치 위치

같은 GitHub Release에서 `pf07-linux-x86_64-1.0.8.tar.gz`와
`SHA256SUMS.txt`를 받고, 압축을 풀기 전에 다음 결과를
`SHA256SUMS.txt`의 해당 줄과 비교합니다.

```sh
sha256sum pf07-linux-x86_64-1.0.8.tar.gz
```

파일명이나 SHA-256이 다르면 실행하지 말고 다시 받습니다. 확인한
`tar.gz` 전체를 임시 폴더가 아닌 새 전용 폴더에 풉니다. 공백·한글
경로도 지원하지만, 실행을 시작한 뒤에는 패키지 폴더를 이동하거나 다른
버전 파일을 덮어쓰지 않습니다. 패키지 루트의 `SHA256SUMS.txt`는 압축
내부 파일 확인에 사용합니다.

## 첫 실행

파일 관리자에서 `PF07-Launcher`를 실행하거나
`PF07-OrderOps.desktop`을 신뢰한 뒤 엽니다. 런처는 Python 3.10 이상,
Docker Engine, Compose 플러그인을 확인하고 누락 시 공식 설치 안내를
브라우저로 엽니다. 설치나 재부팅 후 같은 런처를 다시 열면 패키지 로컬
진행 상태에서 이어갑니다.

허브의 `서비스 시작`을 누르고 서비스 5개가 모두 Ready가 된 뒤 상점과
관리자를 엽니다. 기본 모드는 실제 결제·이메일·HubSpot·Slack을 호출하지
않는 합성 주문용 `DEMO_MODE`입니다. 외부 계정을 연결하는
`CONNECTED_MODE`는 실제 Slack 설정 메시지와 HubSpot·Slack 외부 효과를
만들 수 있으므로 공통 안내를 먼저 읽고 보호된 토큰 파일과 정확한 대상
ID를 준비한 경우에만 사용합니다.

## 다시 실행, 종료, 업데이트

명령 대체 경로는 다음과 같습니다.

```sh
./pf07 status
./pf07 stop
./pf07 start
./pf07 restart
./pf07 recover
./pf07 diagnostics
./pf07 evidence-export
```

`stop`은 컨테이너 서비스를 중지하지만 주문·설정과 패키지 소유 볼륨을
보존합니다. 나중에 같은 폴더의 런처나 `./pf07 start`를 실행하면 같은
상태로 다시 시작합니다. 데이터까지 제거하려면 먼저 암호화 백업을 만든
뒤 확인 문구가 필요한 제거 기능을 사용해야 합니다.

업데이트는 기존 추출본 위에 새 파일을 덮어쓰는 방식이 아닙니다. 검토된
새 버전을 별도 폴더에 풀고 새 허브의 통제된 업데이트에서 지원되는 정확한
이전 추출 폴더를 선택합니다. 모든 런타임 상태는 현재 추출본의 `.pf07/`과
패키지 고유 Compose 프로젝트·볼륨에만 생성됩니다.

암호화 백업·복원·제거·외부 연결·옵션 HTTPS 터널의 정확한 명령과
데이터 영향은
[`packaging/common/PACKAGE-README.ko.md`](packaging/common/PACKAGE-README.ko.md)를
참조합니다. 터널 실패나 중지는 로컬 상점을 중지하지 않습니다.
