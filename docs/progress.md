# 진행 상황

최종 수정 2026-11-26. 다른 기기나 새 세션에서 이어 갈 때 이 문서부터 읽는다. 설계의 원본은 [homeserver-hermes-architecture.md](homeserver-hermes-architecture.md)이고, 이 문서는 "지금 어디까지 왔고 다음에 무엇을 하는지"만 적는다. 단계가 끝날 때마다 갱신한다.

## 한눈에 보기

| 단계 | 상태 | 비고 |
| --- | --- | --- |
| 기반 | 완료 (2026-11-19) | PR #1, #4. 서버에서 Hermes 컨테이너 실행 중 |
| 모델 | 완료 (2026-11-20) | PR #5, #7. GPT OAuth + K-EXAONE fallback |
| Discord | 완료 (2026-11-20) | 사용자가 직접 설정. 봇 연결·허용 사용자 동작 확인 |
| Notion | 완료 (2026-11-20) | PR #8, #10. Hermes Assistant 워크스페이스, integration 연결 |
| Google | **거의 완료** | 캘린더 4개 생성, 토큰 발급·서버 배치(2026-11-26). Discord에서 캘린더 도구 확인 남음 |
| planner MCP v1 | **배포됨, 확인 중** | PR #13 머지·배포, `hermes mcp test planner` 도구 6개. Notion 접근 오류 해결과 Discord 확인 남음 |
| 운영 cron | 대기 | **2026-12-15 전**에 해야 함 (EXAONE 키 2026-12-20 만료) |
| 그 뒤 단계 | 대기 | 아래 "앞으로 할 일" |

## 지금 상태

**서버** (`ssh server`, Tailscale)

- Ubuntu 26.04, Docker. 저장소는 `~/assistant`(`main`), 상태는 `~/assistant-data`(→ 컨테이너 `/opt/data`).
- Hermes `v0.23.2` 컨테이너(`hermes`)가 s6 감독으로 실행 중. 재부팅 후 자동 기동 확인.
- 적용된 설정(`deploy/hermes/configure.sh`): 메인 `gpt-6.2-sol`, 압축 `gpt-6-luna`, `auth.adopt_external_logins: false`, `providers.exaone` + `fallback_providers`(live check `ready`).
- `~/assistant-data/.env`에 Discord·EXAONE·Notion 토큰이 있다(사용자가 직접 넣음). **Claude는 `.env`와 토큰 파일을 읽지 않는다.**
- planner MCP 배포됨(`bc4a7f3`). `~/assistant-data/planner/`에 `planner.yaml`(캘린더 ID 4개)과 `google_token.json`이 있다. Discord 도구는 메모리·세션 검색·planner로 제한됨.

**외부 서비스**

- ChatGPT Plus(`openai-codex`) 로그인 완료. 사용 가능 모델 목록은 `hermes-notes.md`. **2026-11-26 현재 Plus 구독이 끊겨 있다(재구독 검토 중).** 그래서 모든 대화가 K-EXAONE fallback으로 처리된다(`model entitlement`). 의도한 상태다.
- K-EXAONE 키 2026-11-20 발급 → **2026-12-20 만료**. 학습 활용 동의 설정은 확인하지 못함.
- Notion: [비서](https://app.notion.com/p/41da70a526e78172bef2d121718492b8) 페이지 아래 Projects·Milestones·Tasks·Jobs. ID는 [setup/02-notion.md](setup/02-notion.md).
- Google Cloud: Calendar API 사용, 동의 화면 **프로덕션**(미인증, 범위 `calendar.events`), 데스크톱 앱 클라이언트 JSON 받음(사용자 데스크톱에 보관, 저장소 밖). 캘린더 고정·계획·프로젝트·마감은 모두 새 캘린더(기본 캘린더 아님)이고 ID는 서버 `planner.yaml`에만 있다.
- GitHub: 저장소 **공개**. `gh-pages`로 [홈페이지](https://beeean17.github.io/assistant/)·[개인정보처리방침](https://beeean17.github.io/assistant/privacy.html)을 띄워 Google 브랜딩에 사용.

**저장소 브랜치**

| 브랜치 | 내용 |
| --- | --- |
| `main` | PR #13까지 반영 |
| `fix/configure-wait` | `configure.sh` 컨테이너 준비 대기 + 이 문서 갱신. PR #14 |
| `docs/inbox` | 다른 세션이 작업 중인 자료 수집(inbox MCP) 설계. PR #9, 아직 열림 |
| `gh-pages` | Google 브랜딩용 페이지 두 장 |

## 지금 할 일 (순서대로)

1. **Notion 접근 오류:** `list_tasks`가 `object_not_found`(토큰은 유효, 접근 권한 없음). Tasks 데이터 소스는 Hermes Assistant 워크스페이스에 그대로 있다(Claude 커넥터로 확인). 서버 토큰의 integration이 Hermes Assistant 워크스페이스 소속인지, "비서" 페이지에 연결되어 있는지 확인한다(사용자).
2. **Discord 확인:** [setup/03-planner.md](setup/03-planner.md) 4번 표의 다섯 가지. GPT 구독이 없는 동안은 K-EXAONE으로 확인하는 셈이라, 도구 호출이 어색하면 모델 탓일 수 있다.
3. **PR #14 머지.** 다음 배포 때 `configure.sh`가 권한 오류 없이 지나가는지 본다.
4. 확인이 끝나면 설계 문서 구현 순서에서 **Google**, **planner MCP v1**을 체크하고 이 문서를 갱신한다.

## 앞으로 할 일

설계 문서 [구현 순서](homeserver-hermes-architecture.md#구현-순서)를 따른다.

1. **운영 cron (2026-12-15 전):** EXAONE 키 만료 알림 + `hermes fallback check --live`. 첫 cron이라 Hermes cron 형식(일회성·간격)과 `HERMES_TIMEZONE` 적용을 함께 확인한다.
2. **planner MCP 프로젝트 v1:** `list/add/update_project`, `add/update_milestone`, `sync_project_calendar`, Task의 단계 연결.
3. **planner MCP v2:** `propose_plan`, `apply_plan`, 22:30·08:00 cron. cron 초안에 Discord로 답한 메시지가 어느 세션으로 가는지 여기서 시험한다.
4. **planner MCP v3:** `reschedule`, `revert_plan`, 자동 반영, 주간 계획 cron.
5. **planner MCP 프로젝트 v2·v3:** `project_status`(모의 배치), `propose/apply_breakdown`.
6. **jobs MCP:** 수집·중복 제거·알림, Camofox 컨테이너. 시작 전에 채용 공고 소스를 정해야 한다.
7. **고정:** bind mount 제거, 이미지에 `mcp/` 포함, 1\~2주 사용 후 `planner.yaml`·자동 반영 기준 조정.

**남은 미결정 사항** (설계 문서 표 참고)

- 채용 공고 소스: jobs MCP 전
- K-EXAONE 도구 호출 안정성: jobs 단계에서 테스트
- `planner.yaml` 실제 값: 예시 값으로 시작, 2주 뒤 조정
- K-EXAONE 학습 활용 동의 설정 확인: 2026-12-20 키 교체 전

## 알려진 문제와 주의

- **배포 시 컨테이너가 새 이미지로 교체되지 않은 적이 있다.** PR #7 배포 때 이미지 태그는 새 이미지를 가리키는데 컨테이너는 이전 이미지로 계속 돌았다. 지금은 Dockerfile이 코드를 복사하지 않아 영향이 없지만, **고정 단계(이미지에 `mcp/` 포함) 전에 원인을 찾아 `deploy.sh`를 고친다.**
- **배포 직후 `configure.sh`가 권한 오류로 멈춘 적이 있다(2026-11-26).** 컨테이너 init이 `hermes` 사용자 UID를 바꾸기 전에 `uv sync`가 돌아 `/opt/data/.cache`를 만들지 못했다. `configure.sh`가 `hermes`가 `/opt/data`에 쓸 수 있을 때까지 기다리도록 고쳤다. 같은 오류가 다시 나면 `ssh server '~/assistant/deploy/hermes/configure.sh'`만 다시 실행한다.
- **같은 작업 폴더를 여러 세션이 쓰면 브랜치가 섞인다.** 다른 세션의 커밋이 PR #7에 함께 실려 PR #6이 자동으로 머지 처리된 적이 있다. 브랜치를 만들기 전에 `main`이 원격과 같은지 확인하고, 다른 세션이 폴더를 쓰고 있으면 `git worktree add`로 따로 작업한다.
- **비밀 값:** `.env`, `auth.json`, `google_token.json`, 클라이언트 JSON은 열거나 출력하지 않는다. 설정 여부는 사용자에게 묻거나 `hermes status`, `hermes mcp test`, 로그로 확인한다.
- **커밋 이메일:** 이 저장소의 커밋 이메일은 저장소 로컬 설정이라 기기마다 다시 설정해야 한다(값은 사용자에게 확인). 커밋에 Claude 공동 작성자 줄은 넣지 않는다.
- **Notion 커넥터:** Claude의 Notion 커넥터는 Hermes Assistant 워크스페이스에 연결되어 있어야 한다. 처음에 학교 계정 워크스페이스에 잘못 만든 적이 있다(`notion-get-self`로 먼저 확인).
- **EXAONE 429:** live check에서 "service is busy(600)"가 날 수 있다. 서비스 전체 혼잡이라 잠시 뒤 다시 하면 된다.

## 다른 기기에서 이어 하기

```sh
git clone git@github.com:beeean17/assistant.git   # 또는 https
cd assistant
git switch feat/planner-v1        # PR #13이 머지되기 전까지
cd mcp/planner && uv run pytest   # 81 passed
```

- 서버 접속: Tailscale 로그인 후 `~/.ssh/config`에 `Host server`(HostName `server`, User `yoon`)를 넣고 공개 키를 서버에 등록한다. `deploy/deploy.sh`가 이 이름을 쓴다.
- GitHub: `gh auth login`(PR·머지에 사용).
- Google 토큰 발급은 클라이언트 JSON이 있는 기기에서 한다. 다른 기기라면 Google Cloud 클라이언트 화면에서 **보안 비밀 추가**로 새 JSON을 받는다.
- 데스크톱의 로컬 테스트용 이미지와 worktree는 기기마다 따로다. 로컬 Hermes 확인 방법은 `CLAUDE.md` 명령 절.

## 참고 링크

- PR: [#13 planner v1](https://github.com/beeean17/assistant/pull/13), [#9 inbox 설계](https://github.com/beeean17/assistant/pull/9)
- 절차: [01-base](setup/01-base.md), [02-notion](setup/02-notion.md), [03-planner](setup/03-planner.md)
- 외부 사실과 출처: [hermes-notes.md](hermes-notes.md)
