# OFFSET OrderOps · Linux server baseline

이 패키지는 전용 운영 계정과 Docker Engine이 준비된 Linux 서버에
배치하는 격리형 기준선입니다. 일반 데스크톱에서 둘러보려면 Linux local
패키지를 사용합니다. 서버 패키지는 systemd나 nginx를 자동 설치하거나
TLS 인증서를 발급하지 않습니다.

## 안전 경계

- WordPress는 기본적으로 `127.0.0.1`의 선택한 포트에만 바인딩됩니다.
- MariaDB·n8n·Docker API·증거·로그·메트릭에는 공개 경로가 없습니다.
- nginx 예시는 WordPress 상점과 인증이 유지되는 `/wp-admin/`을 한
  origin으로 프록시하며 인증 우회 기능이 없습니다.
- 기본 `DEMO_MODE`는 합성 주문만 사용하고 실제 결제·이메일·HubSpot·Slack을
  호출하지 않습니다. `CONNECTED_MODE`는 실제 Slack 설정 메시지와
  HubSpot·Slack 외부 효과를 만들 수 있으므로 공통 안내를 먼저 읽습니다.

## 1. 다운로드와 첫 실행

필요 환경은 Python 3.10 이상, Docker Engine, Docker Compose 플러그인,
첫 이미지 취득용 인터넷 연결, Docker 사용 권한이 있는 전용 운영
계정입니다. Docker 소켓 접근 권한은 호스트의 높은 권한과 동등할 수
있으므로 이 계정을 다른 용도와 공유하지 않습니다.

같은 GitHub Release에서 `pf07-linux-server-1.0.8.tar.gz`와
`SHA256SUMS.txt`를 받고 압축을 풀기 전에 비교합니다.

```sh
sha256sum pf07-linux-server-1.0.8.tar.gz
```

파일명이나 SHA-256이 다르면 실행하지 않습니다. 확인한 전체 아카이브를
전용 계정이 소유한 새 고정 경로에 풉니다. 아래 예시는 패키지 루트에서
실행합니다.

```sh
cp server/pf07-server.env.example server/pf07-server.env
# server/pf07-server.env에서 사용 중이지 않은 1024~65535 포트를 선택
set -a
. ./server/pf07-server.env
set +a
server/pf07-server preflight
server/pf07-server start
server/pf07-server status
```

`PF07_WORDPRESS_PORT`는 첫 `start`가 `.pf07/runtime.env`를 만들 때
고정됩니다. 이후에는 같은 상태의 포트를 사용합니다. `status` 출력의
상점 URL과 Ready 상태가 실제 접근 주소의 기준입니다. 포트가 이미
사용 중이면 다른 포트를 정한 새 추출본 또는 아직 상태가 없는 이
추출본에서 다시 시작합니다.

## 2. 운영과 데이터

```sh
server/pf07-server status
server/pf07-server stop
server/pf07-server start
server/pf07-server restart
server/pf07-server recover
server/pf07-server diagnostics
server/pf07-server evidence-export
```

`stop`은 서비스를 내리지만 주문·설정, `.pf07/`, 패키지 소유 볼륨을
보존합니다. 같은 경로에서 다시 `start`하면 같은 상태를 사용합니다.
`uninstall --data-choice preserve`도 데이터를 보존하지만,
`--data-choice remove`는 외부 암호화 백업 없이는 되돌릴 수 없습니다.

백업·복원·제거·통제된 업데이트·외부 연결·터널의 정확한 확인 문구와
데이터 영향은
[`packaging/common/PACKAGE-README.ko.md`](packaging/common/PACKAGE-README.ko.md)를
참조합니다. 서버 wrapper는 지원되는 서버 운영 명령만 노출하며, 공통
CLI가 필요한 작업은 패키지 루트의 `launcher/bin/pf07`을 사용합니다.

업데이트는 실행 중인 추출본 위에 덮어쓰지 않습니다. 검토된 새 아카이브를
별도 고정 경로에 풀고, 현재 상태의 외부 암호화 백업을 만든 뒤 새
패키지의 통제된 업데이트에서 지원되는 정확한 이전 추출본을 선택합니다.

## 3. systemd 등록

먼저 위의 수동 `preflight`·`start`·`status`가 통과하는지 확인합니다.
그다음 `pf07-orderops.service.example`의 `User`, `Group`,
`SupplementaryGroups`, `WorkingDirectory`, `EnvironmentFile`,
`ExecStart`, `ExecStop`을 실제 전용 계정·Docker 그룹·절대 경로로
검토하여 바꿉니다. 예시의 `/opt/pf07-orderops`를 그대로 사용했다면:

```sh
sudo install -m 0644 server/pf07-orderops.service.example \
  /etc/systemd/system/pf07-orderops.service
sudo systemctl daemon-reload
sudo systemctl enable --now pf07-orderops.service
sudo systemctl status pf07-orderops.service
server/pf07-server status
```

호스트의 Docker daemon unit 이름이 `docker.service`가 아니면
`Requires`와 `After`도 실제 unit에 맞춥니다. 서비스 파일은
`EnvironmentFile`의 포트를 읽지만, 이미 생성된 `.pf07/runtime.env`의
포트를 바꾸지는 않습니다. 변경 후에는 `systemd-analyze verify`와 실제
시작·중지·재시작을 해당 서버에서 확인합니다.

## 4. nginx와 공개 HTTPS

`nginx-pf07.conf.example`의 hostname, 인증서 경로, upstream 포트를
실제 값으로 바꾸고 호스트의 검토된 nginx include 경로에 설치합니다.
upstream 포트는 `status`가 표시한 포트와 같아야 합니다. nginx 구성
검사 후에만 reload하고, 방화벽은 필요한 HTTPS 포트만 엽니다.
WordPress loopback 포트, MariaDB, n8n, Docker socket은 외부에 열지
않습니다.

TLS 인증서 발급·갱신, DNS, 방화벽, 공개 접근 통제, 실제 서버에서의
브라우저 검수는 이 패키지 밖의 운영 책임입니다. 이 설정을 마치기 전에는
로컬 loopback 모드로만 사용합니다. 옵션 터널은 별도 노출 경로이므로
nginx 공개 배치와 혼용하지 말고, 사용 후 `tunnel-off`와
`tunnel-status`로 종료를 확인합니다.
