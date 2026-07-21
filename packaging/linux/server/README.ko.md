# OddRoom OrderOps · Linux server baseline

이 패키지는 준비된 Linux 서버에서 다시 설계하지 않고 배치할 수 있는 격리형 기준선입니다. 기본 WordPress 바인딩은 `127.0.0.1`이며 MariaDB·n8n·Docker API는 외부에 게시하지 않습니다. 제공된 nginx 예시는 인증이 유지되는 WordPress 상점과 `/wp-admin/` 경로만 동일 origin으로 프록시하며 인증 우회 기능이 없습니다.

1. 전용 운영 계정 아래 새 디렉터리에 전체 아카이브를 풉니다.
2. `server/pf07-server preflight`와 `server/pf07-server start`를 실행합니다.
3. `status`, `stop`, `restart`, `recover`, `diagnostics`, `evidence-export`, `backup`, `restore`, `update`, `tunnel-on/status/off`를 같은 wrapper에서 사용합니다.
4. 서비스로 등록하려면 예시 unit의 `/opt/pf07-orderops`를 실제 절대 배치 경로로 바꾼 뒤 검토하여 설치합니다.
5. 공개 HTTPS는 별도 canonical-CI 터널/리버스 프록시 검증을 통과한 경우에만 켭니다. 로컬 모드는 공개 노출 없이 계속 동작합니다.

패키지 업데이트는 실행 중인 추출본 위에 덮어쓰지 않습니다. 검토된 새 아카이브를 새 디렉터리에 풀고, 암호화된 패키지 로컬 백업과 controlled-update/restore 경로를 사용합니다.
