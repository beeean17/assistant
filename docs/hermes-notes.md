# Hermes·외부 서비스 확인 노트

설계 문서([homeserver-hermes-architecture.md](homeserver-hermes-architecture.md))가 기대는 외부 사실을 출처와 함께 모아 둔다. Hermes는 자주 바뀌므로 구현 전에 해당 항목을 공식 문서로 다시 확인하고, 바뀌었으면 이 파일과 설계 문서를 함께 고친다.

- Hermes 문서: `https://hermes-agent.nousresearch.com/docs` (아래 경로는 이 주소 기준)
- Hermes 저장소: `https://github.com/NousResearch/hermes-agent`
- EXAONE 문서: `https://docs.exaone.ai`

## 확인된 사항 (2026-11-19)

| 주제 | 내용 | 출처 |
| --- | --- | --- |
| Docker 이미지 | `nousresearch/hermes-agent` (`latest`/`stable`, `main`, `X.Y.Z`). 모든 상태가 `/opt/data` 하나에 있다(config.yaml, .env, auth.json, sessions, memories). 부팅 시 config.yaml을 마이그레이션하며 고쳐 쓸 수 있다 | /user-guide/docker, 저장소 `Dockerfile` |
| `uv` | `v0.23.2` 이미지에서 `/opt/hermes/tools/uv-0.13.5-linux-x64/uv`에 있고 PATH에는 없다. `deploy/Dockerfile`이 `ghcr.io/astral-sh/uv:0.13.5`에서 복사해 해결 | 로컬 빌드 확인 (2026-11-19) |
| 이미지 실측 (`v0.23.2`) | 크기 약 4.7GB(Chromium 포함), 대기 메모리 약 320MB. 공식 권장은 메모리 1GB 이상, 브라우저 도구 사용 시 2GB 이상 | 로컬 실행 확인, /user-guide/docker |
| 실행 사용자 | 기본 UID 10000(`hermes`). `HERMES_UID`/`HERMES_GID`(별칭 `PUID`/`PGID`)로 호스트 사용자와 맞추면 `/opt/data` 파일이 호스트 사용자 소유가 된다. `docker exec hermes hermes ...`는 자동으로 `hermes` 사용자로 내려간다 | /user-guide/docker, 로컬 확인 |
| 프로세스 관리 | `gateway run`은 s6-overlay가 감독한다(죽으면 재시작, 컨테이너 재시작 시 이전 상태 복구). ENTRYPOINT(`/init`)를 바꾸지 않는다. 바꾸면 MCP 같은 자식 프로세스 좀비를 거두지 못한다 | /user-guide/docker |
| 로그 | `docker logs`와 `/opt/data/logs/gateways/default/current`(10MB 순환) 양쪽에 남는다 | /user-guide/docker |
| 시간대 | `config.yaml`의 `timezone:` 또는 `HERMES_TIMEZONE`이 에이전트 시계와 cron 일정을 정한다. 로그 시각은 컨테이너 `TZ`를 따른다. cron 작업별 `--timezone`도 있다 | /user-guide/configuration, /user-guide/features/cron |
| ChatGPT 구독 | `hermes auth add openai-codex` (`v0.23.2`의 `hermes status`는 `--type oauth`를 붙인 형태를 안내한다). 기본은 기기 코드, `--browser`는 PKCE. 토큰은 `auth.json`. 갱신이 실패하면 토큰을 격리하고, 다시 로그인해야 풀린다 | /integrations/providers, /user-guide/security |
| 외부 로그인 | `auth.adopt_external_logins: false`로 Codex CLI 토큰을 가져오지 않는다 | /user-guide/security |
| 커스텀 제공자 | `providers.<name>: {api, key_env, transport: chat_completions, default_model, extra_body}`. `custom_providers:` 목록은 구 형식 | /integrations/providers |
| MCP | `mcp_servers.<name>: {command, args, env}`. 환경 변수는 PATH, HOME, USER, LANG, LC_ALL, TERM, SHELL, TMPDIR, XDG_*만 전달된다 | /user-guide/features/mcp |
| 보조 모델 | `auxiliary.compression` 있음. 웹 추출은 LLM을 쓰지 않으므로 `auxiliary.web_extract` 키는 없다. 기본값 `auto`는 메인 모델 | /user-guide/configuration |
| cron | 게이트웨이가 60초마다 확인해 실행한다. `/cron add`, `hermes cron create`, 자연어로 생성. 작업별 `--model --provider`, 모델 결정 순서는 작업 → `cron.model` → 메인. 작업별로 고정한 모델은 `fallback_providers`를 쓰지 않는다. 작업별 `enabled_toolsets`로 도구를 제한한다 | /user-guide/features/cron |
| 도구 제한 | `platform_toolsets.discord: [...]`(`hermes tools`로 설정), 전역 제거는 `agent.disabled_toolsets` | /user-guide/configuration |
| Discord | `DISCORD_ALLOWED_USERS`. Message Content Intent가 없으면 연결이 거부된다. Server Members Intent는 숫자 ID만 쓰면 필요 없다 | /user-guide/messaging/discord |
| 메모리 | MEMORY.md 2,200자, USER.md 1,375자. 세션 검색은 SQLite FTS5. Honcho·Mem0는 플러그인 카탈로그에서 설치(`hermes plugins install honcho`)하고 하나만 활성화된다 | /user-guide/features/memory, /user-guide/features/memory-providers |
| Google Workspace 스킬 | SKILL.md에는 `--services`가 있지만 `scripts/setup.py`에는 그 인자가 없어서 항상 8개 범위(Gmail, Drive 등)를 요청한다. 관련 이슈 #35560, #74128, #109731, #123445. 토큰은 `$HERMES_HOME/google_token.json` | 저장소 스킬 코드 |
| Camofox | 코어에서 빠지고 `camofox` 카탈로그 플러그인이 되었다. 서버 이미지는 `ghcr.io/jo-inc/camofox-browser`, REST 포트는 9377 | plugin-catalog/camofox.yaml |
| `delegate_task` | 호출마다 모델을 지정하는 인자가 없다(의도된 동작, #17685). 전역 `delegation.model`은 동작한다 | GitHub 이슈 #17685, #146382 |
| K-EXAONE API | 2026-11-09부터 당분간 무료. `https://api.exaone.ai/v1` OpenAI 호환, 모델 `k-exaone_v2.5`, 텍스트 전용, 컨텍스트 524,288. 공식 Hermes 설정 예시는 `providers.exaone`, `key_env: EXAONE_API_KEY` | docs.exaone.ai/ko/docs/agent-start |
| K-EXAONE 약관 | 비상업 용도만 허용. 입출력이 기본으로 학습에 쓰이고 opt-out은 소급되지 않는다. API 키는 30일마다 만료된다. 데이터 사용에 동의하면 일일 한도가 오른다. 수치 한도는 공개되지 않았다(초과 시 429, 응답 헤더에 한도 표시) | docs.exaone.ai |
| Codex 모델 목록 (Plus, 2026-11-19) | `gpt-6.2-sol`, `gpt-6.2-astra`, `gpt-6.1-terra`, `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol/terra/luna`, 각 `-900k` 변형. 등급은 Astra(최상위) > Sol(코딩·에이전트) > Terra(균형) > Luna(빠름·대량). Codex 경로 창은 대부분 272K. `hermes model` 선택 화면과 같은 함수(`hermes_cli.codex_models.get_codex_model_ids`)로 확인 | 서버 컨테이너, /integrations/providers |
| 구독 한도 | `hermes usage --provider openai-codex`로 5시간·주간 남은 한도를 본다 | /reference/cli-commands |
| `hermes config set` | 키를 검증하고 저장한다. 모르는 키는 경고만 내고 저장한다(`--force`로 경고 생략). 같은 값을 다시 넣으면 파일이 바뀌지 않는다. `model.provider`를 바꾸면 이전 provider의 `model.base_url`을 지운다 | 로컬 확인 (2026-11-19) |
| 압축 provider | `auxiliary.compression.provider: openai-codex` (`codex`도 같은 값으로 정규화). Codex는 기본 모델이 없으므로 `auxiliary.compression.model`을 꼭 적는다 | 이미지 내 `agent/auxiliary_client.py` |
| 설정 반영 | `compression.*`, `model.context_length`, Discord 허용 목록은 다음 메시지부터 반영된다. 그 밖의 키는 게이트웨이 재시작이 안전하다(`hermes gateway restart`, 컨테이너 안에서는 s6가 처리) | /user-guide/configuration |
| K-EXAONE 공식 Hermes 예시 | `providers.exaone: {api: https://api.exaone.ai/v1, key_env: EXAONE_API_KEY, transport: chat_completions, default_model: k-exaone_v2.5, extra_body: {temperature: 1.0, top_p: 0.95}}`와 전역 `agent.reasoning_effort: medium`. 세션에서는 `/model custom:exaone:k-exaone_v2.5`. 도구 호출 지원 선언은 Hermes 예시에 없다 | docs.exaone.ai/ko/docs/agent-start |
| fallback | 최상위 `fallback_providers: [{provider, model}]`. `providers:`에 등록한 이름을 그대로 쓴다(`provider: exaone`). 429·5xx(재시도 후), 401·403·404(즉시)에서 전환하고, 턴 단위로 다음 메시지에서 주 모델을 다시 시도한다. 리셋 시각이 알려진 한도 초과는 리셋까지 유지한다. 모델을 지정한 cron은 fallback을 타지 않는다. 환경 변수로는 설정할 수 없다. `hermes fallback check [--live]`로 점검(실패 시 종료 코드 1) | /integrations/providers#fallback-providers |
| Google OAuth 프로덕션 게시 | Google Auth Platform의 "앱 게시" 버튼은 브랜딩에 앱 이름·지원 이메일·개발자 연락처 외에 **홈페이지 URL과 개인정보처리방침 URL**이 있고, 그 도메인이 승인된 도메인에 있어야 켜진다(버튼 툴팁). 공식 문서가 아니라 2026년 8~10월 포럼 보고로 확인 | discuss.google.dev(Cloud Foundations & Onboarding), 사용자 화면 (2026-11-22) |
| K-EXAONE 학습 활용 동의 | Rate Limits 문서: 마이 프로필 > 동의 및 알림 관리 > "(선택) 동의: AI 모델 학습 및 서비스 개선을 위한 이용 기록 분석". 동의하면 일일 한도가 늘어나고, 동의하지 않아도 API는 쓸 수 있다. 위 약관 요약("기본으로 학습에 쓰임")과 설명이 다르다. 한도는 `x-{second,minute,day}-rate-limit[-remaining]` 응답 헤더로 확인 | docs.exaone.ai/ko/docs/rate-limits |
| K-EXAONE 키 점검 | `GET https://api.exaone.ai/v1/models`(Bearer 키)가 200과 `k-exaone_v2.5`를 돌려주면 키가 유효하다. 개인 데이터를 보내지 않는다 | 서버 확인 (2026-11-20) |
| K-EXAONE `reasoning_effort` | `low`, `high`, `max`만 받고 기본값은 `max`. 공식 Hermes 예시는 `medium`을 쓰므로 실제 동작을 확인해야 한다 | docs.exaone.ai 모델 레퍼런스 |

| MCP `env`의 `${VAR}` | `env`·`args`·`url`·`headers` 값의 `${VAR}`(또는 `${env:VAR}`)는 연결할 때 프로필 `.env`에서 채워진다. 값 전체가 설정되지 않은 변수 하나면 그 항목은 아예 빠진다. `hermes config set`은 `${NOTION_TOKEN}`을 글자 그대로 저장한다 | /reference/mcp-config-reference, 로컬 확인 (2026-11-22) |
| MCP 등록 형식 | `mcp_servers.<name>: {command, args, env, cwd, timeout, connect_timeout, tools}`. 도구 이름은 `mcp_<server>_<tool>`, 툴셋 이름은 `mcp-<server>`. 게이트웨이는 `config.yaml` 변경을 1분 안에 반영한다 | /user-guide/features/mcp |
| MCP 연결 점검 | `hermes mcp test <name>`: 연결 시간과 발견한 도구 목록을 보여 준다 | /reference/cli-commands, 로컬 확인 |
| 플랫폼별 MCP 범위 | `platform_toolsets.<platform>` 목록에 MCP 서버 이름이 하나도 없으면 활성 서버 전부, 이름이 있으면 그 서버만, `no_mcp`면 없음. 빈 목록 `[]`은 MCP도 없음 | /reference/toolsets-reference |
| MCP Python SDK | `mcp` 2.x에서 FastMCP가 `MCPServer`로 바뀌었다(`from mcp.server.mcpserver import MCPServer`). `@server.tool()`, `server.run("stdio")`, 예상한 실패는 `ToolError` | 설치된 `mcp` 2.3.0 소스 |
| Notion API | 최신 버전 `2026-03-11`(2025-09-03 이후 유일). 데이터 소스 조회 `POST /v1/data_sources/{id}/query`, 스키마 `GET /v1/data_sources/{id}`(status `options`·`groups[].option_ids`), 페이지 생성 parent `{"type": "data_source_id", ...}`. `archived`는 `in_trash`로 바뀜. 다음 버전은 Markdown v2가 기본이 될 예정 | developers.notion.com/reference/changes-by-version, /reference/post-page (2026-11-22) |

## 구현할 때 확인할 것

- [ ] `HERMES_TIMEZONE=Asia/Seoul`이 cron 일정에 실제로 적용되는지 (첫 cron을 만들 때 다음 실행 시각으로 확인)
- [ ] K-EXAONE 도구 호출(`tools` 인자) 지원 여부와 안정성
- [ ] 키 만료 알림 같은 일회성·간격 cron을 어떤 형식으로 만드는지
- [ ] Google OAuth "프로덕션" 게시 상태에서 refresh token이 만료되지 않는지 (Google 공식 문서)
