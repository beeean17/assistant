# assistant

홈서버의 Hermes Agent 위에서 Discord로 대화하는 개인 비서. 이 저장소는 설계 문서, MCP 서버(planner, jobs), 배포 설정을 함께 둔다.

대상 서버는 x86_64 Ubuntu Server(i5-7200U, 2코어 4스레드, RAM 12GB) 한 대다. 이 서버에 저장소를 clone해 Docker 이미지를 직접 빌드하고 Compose로 실행한다. 레지스트리는 쓰지 않는다. 의존성과 리소스는 이 사양 기준으로 고른다.

## 기준 문서

- `docs/homeserver-hermes-architecture.md`: 설계의 원본. 작업 전에 관련 절을 읽고 그대로 따른다.
- `docs/hermes-notes.md`: Hermes·K-EXAONE·Google 등 외부 사실과 출처. 설정 키나 명령을 쓰기 전에 여기서 확인한다.

## 진행 방식

- 설계 문서의 **구현 순서**를 위에서부터 진행한다. 한 단계 = 한 브랜치(`feat/planner-v1` 등), 끝나면 해당 항목을 체크한다.
- 진행하려는 단계에 걸린 **미결정 사항**이 남아 있으면 구현 전에 사용자에게 묻는다. 추측으로 채우지 않는다.
- 구현 중 설계와 달라져야 하면 코드보다 문서를 먼저 고치고, **결정 기록**에 날짜와 이유를 남긴다. 문서와 코드가 어긋난 채로 두지 않는다.
- Hermes 설정 키, CLI 명령, 이미지 구조는 자주 바뀐다. 기억에 의존하지 말고 공식 문서로 확인한 뒤 `hermes-notes.md`에 확인일과 출처를 갱신한다.
- 서버(SSH) 작업, 계정 로그인, 외부 서비스 설정(Discord, Notion, Google Cloud)은 사용자가 한다. Claude는 절차와 설정 파일을 준비한다.

## 설계 원칙 (코드에서 지킬 것)

- 시간 계산, 빈 시간 계산, 블록 배치, 중복 판단은 코드로 한다. LLM에게 넘기는 도구 설명에 계산을 맡기는 표현을 쓰지 않는다.
- Calendar·Notion 쓰기는 `propose_plan` → 승인 → `apply_plan` 흐름을 지킨다. 자동 반영 여부는 코드가 판단해 반환한다(설계 문서의 "자동 반영 기준").
- 에이전트가 만든 Calendar 이벤트에는 `extendedProperties.private`에 `task_id`, `plan_id`, `kind`를 넣는다.
- Calendar·Notion 자격 증명은 planner MCP만 가진다. 개인 데이터를 K-EXAONE으로 보내는 경로를 만들지 않는다.

## 코드 규칙

- Python, MCP 하나당 `mcp/<name>/`의 독립 uv 프로젝트. FastMCP stdio 서버.
- 서버 진입점은 얇게 두고, 배치 알고리즘 같은 로직은 순수 함수 모듈로 분리해 pytest로 테스트한다.
- 시각은 항상 timezone-aware(`Asia/Seoul`)로 다룬다. 자정을 넘는 하루(예: 08:30~01:00), 주 경계(월요일 시작), 블록 분할, 시간 부족 표시는 테스트로 고정한다.
- 외부 API(Notion, Google)는 얇은 클라이언트 계층 뒤에 두고, 테스트에서는 가짜 구현으로 바꾼다. 테스트가 실제 계정에 쓰지 않게 한다.
- 비밀 값은 커밋하지 않는다. `.env.example`, `planner.yaml.example`만 저장소에 둔다.

## 문서 작성

- 문서는 한국어, 짧은 평서문("~한다")으로 쓴다. 기존 문서의 표·목록 형식을 따른다.
- 코드 식별자와 주석은 영어로 쓴다.

## 명령

- 로컬 확인(데스크톱도 x86_64): 저장소 밖 임시 디렉터리를 `DATA_DIR`로 둔 env 파일을 만들고
  `docker compose -f deploy/compose.yaml --env-file <임시.env> up -d --build`. 확인이 끝나면 `down`하고 임시 데이터를 지운다.
- 서버 배포: 데스크톱에서 `deploy/deploy.sh` (SSH 호스트 `homeserver`, `ASSISTANT_HOST`로 변경). push된 `origin/main`만 배포된다. 서버 설치 절차는 `docs/setup/01-base.md`.
- GitHub Actions는 CI(테스트)에만 쓴다. 서버에 접근하는 워크플로는 만들지 않는다.
- 컨테이너 안 Hermes 명령: `docker compose -f deploy/compose.yaml exec hermes hermes <명령>`.
