# planner MCP v1: Google 토큰, planner.yaml, 배포와 확인

planner MCP v1(`list/add/update/complete_task`, `get_day`, `find_free_slots`)을 서버에서 쓰기 위한 절차다. Google 단계의 마지막 작업인 토큰 발급도 여기서 한다.

**완료 기준**

- [x] 서버 `~/assistant-data/planner/`에 `planner.yaml`과 `google_token.json`이 있다.
- [x] `hermes mcp test planner`가 연결되고 도구 6개를 보여 준다.
- [x] Discord에서 "할 일 목록 보여 줘", "오늘 일정 보여 줘"에 Notion·Calendar 내용으로 답한다. (2026-11-26, 4번 표 다섯 가지와 고정 일정 반영 확인)

## 1. Google 토큰 발급 (데스크톱, 직접)

준비물: Google Cloud에서 받은 OAuth 클라이언트 JSON(데스크톱 앱). 저장소 밖, 예를 들어 `~/.config/assistant/client_secret.json`에 둔다.

```sh
cd ~/code/assistant/mcp/planner
uv run --extra auth python -m planner.google_auth \
  --client-secret ~/.config/assistant/client_secret.json \
  --out ~/.config/assistant/google_token.json
```

1. 브라우저가 열리면 캘린더를 쓰는 Google 계정으로 로그인한다.
2. "확인되지 않은 앱" 경고가 나오면 **고급 → (앱 이름)으로 이동**을 누른다.
3. 권한은 "캘린더의 일정 보기 및 수정" 하나다. 허용하면 터미널에 `wrote …google_token.json`이 나온다.

토큰 파일은 권한 600으로 만들어지고, 내용은 화면에 나오지 않는다. 대화나 저장소에 붙여 넣지 않는다.

서버로 옮긴다.

```sh
ssh server 'mkdir -p ~/assistant-data/planner && chmod 700 ~/assistant-data/planner'
scp ~/.config/assistant/google_token.json server:~/assistant-data/planner/google_token.json
ssh server 'chmod 600 ~/assistant-data/planner/google_token.json'
```

## 2. planner.yaml (서버)

```sh
ssh server
cp ~/assistant/deploy/planner.yaml.example ~/assistant-data/planner/planner.yaml
nano ~/assistant-data/planner/planner.yaml
```

`calendars`의 `CHANGE_ME` 네 곳을 실제 캘린더 ID로 바꾼다(Google Calendar → 설정 → 캘린더 통합 → 캘린더 ID). 기본 캘린더를 "고정"으로 쓰면 그 ID는 Gmail 주소다. 나머지 값은 설계 문서의 예시 값이며 1\~2주 써 본 뒤 조정한다.

이 파일은 비밀 값이 아니다. 캘린더 ID만 들어 있다.

## 3. 배포 (데스크톱)

```sh
deploy/deploy.sh
```

배포 스크립트가 컨테이너를 다시 띄운 뒤 `deploy/hermes/configure.sh`를 실행한다.

- planner 의존성을 `/opt/data/planner/.venv`에 설치한다(처음 한 번 수십 초).
- `mcp_servers.planner`와 `platform_toolsets.discord: [memory, session_search, planner]`를 설정한다. 이때부터 Discord에서는 메모리, 세션 검색, planner 도구만 쓴다.
- 설정이 바뀌었으면 게이트웨이를 재시작한다.

## 4. 확인

```sh
ssh server 'docker exec hermes hermes mcp test planner'
```

`✓ Connected`와 `✓ Tools discovered: 6`이 나오면 연결된 것이다. 그다음 Discord에서 확인한다.

| 보낼 말 | 기대 |
| --- | --- |
| 할 일 목록 보여 줘 | Notion Tasks의 열린 할 일(없으면 빈 목록) |
| "테스트 할 일" 추가해 줘, 1시간, 내일까지 | Notion Tasks에 새 항목 |
| 그거 완료로 바꿔 줘 | 상태 `완료`, 남은 시간 0 |
| 오늘 일정 보여 줘 | 고정 일정, 식사 시간, 빈 시간 |
| 이번 주 빈 시간 알려 줘 | 날짜별 빈 시간과 배치 가능 시간 |

**자주 나는 오류**

| 메시지 | 원인 |
| --- | --- |
| `planner config not found` | 2번의 `planner.yaml`이 없다 |
| `Notion rejected the token` | `.env`의 `NOTION_TOKEN`이 틀렸다 |
| `object_not_found: Could not find database …` | 토큰은 유효하지만 integration이 "비서" 페이지에 연결되지 않았거나 다른 워크스페이스 소속이다 |
| `Google token file not found` | 1번의 토큰 파일이 서버에 없다 |
| `Google token file is missing refresh_token, client_id, client_secret` | 토큰 대신 Google Cloud에서 받은 클라이언트 JSON을 올렸다. 클라이언트 JSON은 1번 명령의 입력이고, 서버에는 그 명령이 만든 파일을 올린다 |
| `Calendar '…' not found` | `planner.yaml`의 캘린더 ID가 틀렸다 |
| `refresh token was revoked or expired` | Google 권한을 취소했거나 동의 화면이 테스트 상태다. 1번을 다시 한다 |
