# OFFSET OrderOps 패키지

이 패키지는 자격 증명 없이 시작하는 `DEMO_MODE` 실행본입니다. 합성 주문만 사용하고 실제 결제, 이메일, HubSpot, Slack을 호출하지 않습니다.

## 다운로드 확인

운영체제용 실행 패키지와 `SHA256SUMS.txt`를 같은 GitHub Release에서
받고, 압축을 풀기 전에 외부 아카이브의 SHA-256을 비교합니다. 압축을
푼 뒤에는 패키지 루트의 `SHA256SUMS.txt`로 내부 파일을 확인할 수
있습니다. 파일명이나 해시가 다르면 실행하지 말고 다시 받습니다.

## 필요 환경과 첫 실행

- 패키지별 안내에 기록된 Docker-compatible 런타임과 `docker compose`
- Python 3.10 이상
- 첫 설치 시 WordPress 고정 버전 의존성을 받을 인터넷 연결

그래픽 런처가 필수 구성요소를 먼저 검사합니다. 누락 시 공식 설치 페이지와 번호 순서를 표시하고, 다음 런처 실행에서 다시 검사해 이어갑니다. Docker Desktop은 현재 약관상 자격이 확인된 경우에만 선택 가능한 대안이며, Windows/macOS의 기본 0-KRW 경로는 Moby 엔진을 사용하는 Rancher Desktop입니다.

## 그래픽 실행 허브

Linux 또는 macOS 터미널에서 패키지 루트를 열고 실행합니다.

```sh
./launcher/bin/pf07-hub
```

브라우저에서 `서비스 시작`을 누르고 준비 완료를 확인한 뒤 `상점 열기`
또는 `관리자 열기`를 사용하세요. 관리자 비밀번호는 첫 시작에 패키지
내부에서 생성됩니다. 허브의 `주문 관리 계정 보기` 또는 패키지 로컬
`credentials` CLI로 확인합니다.

## CLI

```sh
./launcher/bin/pf07 --help
./launcher/bin/pf07 preflight
./launcher/bin/pf07 start
./launcher/bin/pf07 status
./launcher/bin/pf07 credentials
./launcher/bin/pf07 open-store
./launcher/bin/pf07 open-admin
./launcher/bin/pf07 stop
./launcher/bin/pf07 restart
./launcher/bin/pf07 recover
./launcher/bin/pf07 diagnostics
./launcher/bin/pf07 evidence-export
./launcher/bin/pf07 backup --passphrase-file /외부/경로/passphrase.txt
./launcher/bin/pf07 restore /외부/경로/backup.pf07backup --passphrase-file /외부/경로/passphrase.txt --confirm 'RESTORE PF07'
./launcher/bin/pf07 update '/기존/PF07 추출 폴더' --confirm 'UPDATE PF07'
./launcher/bin/pf07 tunnel-on --provider cloudflared --executable /외부/경로/cloudflared --confirm 'ENABLE PF07 TUNNEL'
./launcher/bin/pf07 tunnel-status
./launcher/bin/pf07 tunnel-off --confirm 'DISABLE PF07 TUNNEL'
./launcher/bin/pf07 uninstall --data-choice preserve --confirm 'UNINSTALL PF07'
```

`--help`는 언어·데모 시나리오·데모 데이터 초기화·외부 연결을 포함한 전체
하위 명령을 표시합니다. 데이터를 바꾸거나 외부 효과를 만들 수 있는
명령은 해당 하위 명령의 `--help`와 확인 문구를 먼저 확인합니다.

`credentials` 출력에는 생성된 로컬 관리자 비밀번호가 포함됩니다.
채팅, 로그, 스크린샷, Git에 기록하지 마십시오.

`stop`은 서비스를 중지하고 로컬 데이터와 패키지 소유 볼륨을
보존합니다. 다시 `start`하면 같은 상태를 사용합니다. 실행 상태와
생성된 재료는 패키지 루트의 `.pf07/`과 고유 Compose 자원에 저장됩니다.

한국어와 English는 한 패키지, 한 Compose 프로젝트, 한 WordPress DB, 한 n8n 런타임, 한 `SHOP_INSTANCE_ID` 위에서 표시만 전환합니다. 언어 변경은 주문·이벤트·외부 효과를 새로 만들지 않습니다.

그래픽 허브에서도 진단, 재시작/복구, 증거 ZIP, 인증된 암호화 백업/복원, 통제된 업데이트, 옵션 HTTPS 터널, 확인된 패키지 범위 제거를 사용할 수 있습니다. 백업 passphrase는 아카이브에 저장되지 않으므로 별도로 보관해야 합니다.

## DEMO와 외부 연결

`DEMO_MODE`는 실제 HubSpot·Slack을 호출하지 않습니다. `CONNECTED_MODE`
를 사용하려면 먼저 `connected-setup --help`에 표시되는 토큰 파일,
HubSpot pipeline/stage ID, Slack channel ID를 준비해야 합니다. 토큰
파일은 패키지 밖의 보호 경로에 두고 값을 명령행이나 문서에 직접
쓰지 않습니다.

`connected-setup`은 정확한 확인 문구와 함께 한 건의 합성 Slack 설정
메시지를 실제 채널로 전송합니다. 이후 `CONNECTED_MODE`의 합성 주문은
설정된 HubSpot·Slack에 실제 외부 효과를 만들 수 있습니다. 실제 결제
및 실제 이메일 발송은 포함하지 않습니다.

Ready 상태의 `DEMO_MODE`를 먼저 시작한 뒤, 실제 대상을 다시 확인하고
다음 형식으로 연결합니다.

```sh
./launcher/bin/pf07 connected-setup \
  --hubspot-token-file /보호/경로/hubspot-token.txt \
  --hubspot-pipeline-id '실제_PIPELINE_ID' \
  --hubspot-initial-stage-id '실제_STAGE_ID' \
  --slack-token-file /보호/경로/slack-token.txt \
  --slack-channel-id '실제_CHANNEL_ID' \
  --confirm-slack-test 'SEND PF07 SLACK TEST'
```

이 명령은 연결 검사 뒤 모드를 `CONNECTED_MODE`로 바꿉니다. 합성 주문의
외부 전송을 멈추고 로컬 데모로 돌아가려면
`./launcher/bin/pf07 mode DEMO_MODE`를 사용하고 `status`로 현재 모드를
확인합니다.

## 백업·복원·제거

- `backup`은 패키지 상태와 세 볼륨을 인증·암호화한 외부
  `.pf07backup`으로 만듭니다.
- passphrase를 잃으면 백업을 복구할 수 없습니다. 아카이브와 분리해
  보관합니다.
- `restore`는 현재 런타임이 있으면 선택한 아카이브 옆에 같은
  passphrase로 `PF07-Pre-Restore-*.pf07backup` 사전본을 자동 생성한
  뒤, 현재 writer를 중지하고 세 볼륨을 선택한 백업 상태로 교체하여
  런타임을 다시 시작합니다. 자동 사전본도 선택한 아카이브와 함께
  보관합니다.
- `uninstall --data-choice preserve`는 실행 자원을 내리지만 데이터와
  패키지 상태를 보존합니다.
- `uninstall --data-choice remove`는 패키지 소유 볼륨과 `.pf07` 상태를
  제거합니다. 외부 백업 없이는 되돌릴 수 없습니다.

데이터까지 제거할 때는 한 명령에서 외부 백업을 먼저 만들 수 있습니다.

```sh
./launcher/bin/pf07 uninstall \
  --data-choice remove \
  --backup-output /외부/경로/PF07-before-uninstall.pf07backup \
  --backup-passphrase-file /보호/경로/passphrase.txt \
  --confirm 'UNINSTALL PF07'
```

## 업데이트와 터널

업데이트는 기존 추출본을 덮어쓰지 않습니다. 검토된 새 아카이브를 별도
폴더에 풀고 새 허브에서 지원되는 정확한 이전 추출 폴더를 선택합니다.
PF07 1.0.7의 controlled update 입력은 정확한 검토 완료 1.0.6
추출본입니다. 다른 버전이나 이미 실행 상태를 소유한 새 추출본은
선택하지 않습니다.

터널은 준비된 로컬 런타임에만 선택적으로 추가되며 꺼지거나 실패해도
로컬 모드는 계속 동작합니다. `cloudflared`나 ngrok CLI·자격 구성은
패키지 밖에 두며, 패키지는 상점과 WordPress 인증 관리 경로만
허용합니다. 사용 후 `tunnel-off`와 `tunnel-status`로 외부 노출 종료를
확인합니다.
