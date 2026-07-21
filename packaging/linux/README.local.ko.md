# OddRoom OrderOps · Linux local

ZIP이 아닌 `tar.gz` 전체를 공백·한글을 포함할 수 있는 새 폴더에 풉니다. 파일 관리자에서 `PF07-Launcher`를 실행하거나 `PF07-OrderOps.desktop`을 신뢰한 뒤 엽니다. 런처는 Python 3.10+, Docker Engine, Compose 플러그인을 검사하고 누락 시 공식 설치 안내를 브라우저로 엽니다. 설치 후 다시 실행하면 같은 패키지 진행 상태에서 재검사합니다.

허브의 `런타임 시작`이 다섯 서비스를 모두 Ready로 표시한 뒤 상점/관리자를 엽니다. 명령 대체 경로는 `./pf07 status`, `./pf07 restart`, `./pf07 diagnostics`, `./pf07 evidence-export`입니다. 백업·복원·업데이트·옵션 HTTPS 터널은 같은 허브와 CLI에서 제공하며, 터널 실패/중지는 로컬 상점을 중지하지 않습니다. 모든 런타임 상태는 이 추출본의 `.pf07/`과 패키지 고유 Compose 프로젝트/볼륨에만 생성됩니다.
