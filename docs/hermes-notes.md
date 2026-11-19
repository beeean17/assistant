# Hermes·외부 서비스 확인 노트

설계 문서([homeserver-hermes-architecture.md](homeserver-hermes-architecture.md))가 기대는 외부 사실을 출처와 함께 모아 둔다. Hermes는 자주 바뀌므로 구현 전에 해당 항목을 공식 문서로 다시 확인하고, 바뀌었으면 이 파일과 설계 문서를 함께 고친다.

- Hermes 문서: `https://hermes-agent.nousresearch.com/docs` (아래 경로는 이 주소 기준)
- Hermes 저장소: `https://github.com/NousResearch/hermes-agent`
- EXAONE 문서: `https://docs.exaone.ai`

## 확인된 사항 (2026-11-19)

| 주제 | 내용 | 출처 |
| --- | --- | --- |
| Docker 이미지 | `nousresearch/hermes-agent` (`latest`/`stable`, `main`, `X.Y.Z`). 모든 상태가 `/opt/data` 하나에 있다(config.yaml, .env, auth.json, sessions, memories). 부팅 시 config.yaml을 마이그레이션하며 고쳐 쓸 수 있다 | /user-guide/docker, 저장소 `Dockerfile` |
| `uv` | Dockerfile이 `/opt/hermes/tools`에 고정 버전 uv를 두지만 `/usr/local/bin`에는 링크하지 않는다. PATH에 있는지는 미확인 | 저장소 `Dockerfile` |
| ChatGPT 구독 | `hermes auth add openai-codex`. 기본은 기기 코드, `--browser`는 PKCE. 토큰은 `auth.json`. 갱신이 실패하면 토큰을 격리하고, 다시 로그인해야 풀린다 | /integrations/providers, /user-guide/security |
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
| K-EXAONE `reasoning_effort` | `low`, `high`, `max`만 받고 기본값은 `max`. 공식 Hermes 예시는 `medium`을 쓰므로 실제 동작을 확인해야 한다 | docs.exaone.ai 모델 레퍼런스 |

## 구현할 때 확인할 것

- [ ] 공식 이미지에서 `uv`가 PATH에 있는지: `docker run --rm nousresearch/hermes-agent which uv`
- [ ] `mcp_servers.*.env`에서 `${VAR}` 치환이 되는지, 아니면 값을 직접 적어야 하는지
- [ ] Hermes cron이 컨테이너 `TZ`를 따르는지, 별도 timezone 설정이 있는지
- [ ] `openai-codex`에서 쓸 수 있는 모델 ID (메인, 상위, 경량)
- [ ] K-EXAONE 도구 호출(`tools` 인자) 지원 여부와 안정성
- [ ] 키 만료 알림 같은 일회성·간격 cron을 어떤 형식으로 만드는지
- [ ] Google OAuth "프로덕션" 게시 상태에서 refresh token이 만료되지 않는지 (Google 공식 문서)
