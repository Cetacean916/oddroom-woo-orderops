# OFFSET OrderOps 패키지

이 패키지는 자격 증명 없이 시작하는 `DEMO_MODE` 실행본입니다. 합성 주문만 사용하고 실제 결제, 이메일, HubSpot, Slack을 호출하지 않습니다.

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

브라우저에서 `데모 시작`을 누른 뒤 `상점 열기` 또는 `관리자 열기`를 사용하세요. 관리자 비밀번호는 첫 시작에 패키지 내부에서 생성되며 허브의 `로컬 관리자 자격 증명 보기`에서만 확인합니다.

## CLI

```sh
./launcher/bin/pf07 start
./launcher/bin/pf07 status
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

`stop`은 컨테이너만 중지하고 로컬 데이터를 보존합니다. 실행 상태와 생성된 재료는 패키지 루트의 `.pf07/`에만 저장됩니다.

한국어와 English는 한 패키지, 한 Compose 프로젝트, 한 WordPress DB, 한 n8n 런타임, 한 `SHOP_INSTANCE_ID` 위에서 표시만 전환합니다. 언어 변경은 주문·이벤트·외부 효과를 새로 만들지 않습니다.

그래픽 허브에서도 진단, 재시작/복구, 증거 ZIP, 인증된 암호화 백업/복원, 통제된 업데이트, 옵션 HTTPS 터널, 확인된 패키지 범위 제거를 사용할 수 있습니다. 백업 passphrase는 아카이브에 저장되지 않으므로 별도로 보관해야 합니다.

업데이트는 기존 추출본을 덮어쓰지 않습니다. 검토된 새 아카이브를 별도 폴더에 풀고 새 허브에서 기존 추출 폴더를 선택합니다. 터널은 준비된 로컬 런타임에만 선택적으로 추가되며 꺼지거나 실패해도 로컬 모드는 계속 동작합니다. `cloudflared`나 ngrok CLI·자격 구성은 패키지 밖에 두며, 패키지는 상점과 WordPress 인증 관리 경로만 허용합니다.
