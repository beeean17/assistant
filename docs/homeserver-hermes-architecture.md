# 홈서버 Hermes 개인 비서 설계

Nov 19, 2026 · @성빈 · 최종 수정 Nov 19, 2026

## 개요

홈서버에 Hermes Agent를 Docker로 띄우고, 기능별 MCP를 붙여 Discord로 대화하는 개인 비서를 만든다. 일정의 원본과 알림은 Google Calendar, 할 일의 원본은 Notion이 맡고, Hermes는 둘을 잇는다.

**핵심 기능**

- **미래 일정 관리**: 고정 일정 사이 빈 시간에 할 일과 루틴을 시간 블록으로 배치하고, 변경이 생기면 다시 배치한다.
- **채용 공고 알림**: 금융권 IT·데이터·핀테크 공고를 주기적으로 수집해 새 공고만 Discord로 알린다.
- **대화 기억**: 가끔 나누는 대화에서 중요한 내용을 기억하고, 과거 대화를 검색한다.

**범위 밖**: 코딩 작업, 실제 행동 기록(트래킹).

**원칙**

- 시간 계산과 중복 판단은 코드가, 자연어 해석과 판단은 LLM이 맡는다.
- 에이전트가 만든 변경(계획 초안, 해석한 일정, 추정한 소요 시간)은 Discord에서 승인받은 뒤 반영한다. 단, [자동 반영 기준](#자동-반영-기준)에 맞는 작은 재배치는 반영 후 알린다.
- 사용자가 직접 지시한 쓰기("ERD 끝", "이거 저장")는 그 지시를 승인으로 본다.
- 개인 데이터(일정, 할 일, 대화)는 학습에 쓰이는 외부 API로 보내지 않는다.
- 서드파티 스킬과 플러그인은 코드를 직접 읽어 본 것만 설치한다.

## 전체 구조

```
 Discord (폰·PC)
     │
┌────▼──────────── hermes 컨테이너 ─────────────┐      ┌─ camofox 컨테이너 ─┐
│ gateway · cron · memory                       │      │ 안티디텍션 브라우저 │
│  ├─ planner MCP ──► Notion API                │      │ REST :9377          │
│  │              └─► Google Calendar API       │      └──────────▲──────────┘
│  └─ jobs MCP ─────► 채용 사이트 ──(막힐 때만)──┼─────────────────┘
└───────┬───────────────────────────────────────┘
        ├─► ChatGPT 구독 (openai-codex): 대화, 계획, 컨텍스트 압축
        └─► K-EXAONE API: 채용 공고 수집·요약만
```

Discord가 유일한 입력 창구다. 시간은 Google Calendar, 할 일은 Notion이 원본이고, Hermes는 MCP로 둘을 읽고 쓴다. Calendar와 Notion에 접근하는 자격 증명은 planner MCP만 가진다.

## 모델 배분

대화와 판단, 개인 데이터를 다루는 작업은 모두 ChatGPT 구독(OAuth)으로 처리한다. K-EXAONE은 공개 데이터인 채용 공고에만 쓴다. Claude API는 쓰지 않는다.

| 작업 | 모델 | 지정 방법 |
| --- | --- | --- |
| Discord 대화, 일정 조정 | GPT (ChatGPT 구독, `openai-codex`) | 메인 모델 |
| 주간 계획 | GPT 상위 모델 | cron 작업별 `--model` |
| 컨텍스트 압축 | GPT 경량 모델 (구독 내) | `auxiliary.compression` |
| 채용 공고 수집·요약 | K-EXAONE 2.5 | cron 작업별 `--model --provider` |

**연결**

- GPT: `hermes auth add openai-codex`로 기기 코드 로그인. `auth.adopt_external_logins: false`로 Codex CLI 토큰을 가져오지 않게 한다.
- K-EXAONE: `providers.exaone`으로 등록한다. base URL `https://api.exaone.ai/v1`, 모델 ID `k-exaone_v2.5`, 키는 `EXAONE_API_KEY`. 형식은 [hermes-notes.md](hermes-notes.md) 참고.
- cron 모델 결정 순서: 작업별 지정 → `cron.model` → 메인 모델. 작업별로 고정한 모델은 `fallback_providers`를 쓰지 않는다.
- 웹 추출은 LLM을 쓰지 않으므로 모델을 따로 지정하지 않는다.

**주의**

- ChatGPT 구독 사용량은 Codex·Work 한도에서 차감된다. 보조 작업은 기본값(`auto`)이면 메인 모델로 처리되므로 압축은 경량 모델로 따로 지정한다.
- Codex CLI와 Hermes는 각자 로그인한다. refresh token을 복사해 공유하면 한쪽이 401로 끊긴다.
- Codex 토큰 갱신이 실패하면 Hermes가 토큰을 격리하고, 다시 로그인하기 전까지 cron이 멈춘다. 08:00 요약이 오지 않으면 이것부터 확인한다.
- K-EXAONE 약관: 비상업 용도만 허용되고, 입출력이 기본으로 학습에 쓰인다(opt-out은 소급되지 않음). API 키는 30일마다 만료된다.
  - 키를 처음 발급할 때 학습 opt-out을 먼저 적용한다.
  - 만료 5일 전 Discord 알림을 cron으로 둔다.
  - `reasoning_effort`는 기본값이 `max`이므로 수집 작업에는 `low`로 명시한다.
- `delegate_task`는 호출마다 모델을 지정할 수 없다(의도된 동작). 위임은 쓰지 않는다.
- K-EXAONE의 도구 호출이 불안정하면 해당 작업만 GPT 경량 모델로 옮긴다.

## Notion 스키마

Notion은 할 일의 원본이다. 반복은 Notion에 만들지 않고 규칙 파일과 Calendar 반복 일정으로 처리한다.

**Projects**

| 속성 | 타입 | 비고 |
| --- | --- | --- |
| 이름 | Title |  |
| 분류 | Select | 수업 / 개인 / 취업 / 동아리 |
| 기간 | Date (범위) | "프로젝트" 캘린더에 막대로 반영 |
| 상태 | Status | 진행 / 보류 / 완료 |

**Tasks**

| 속성 | 타입 | 비고 |
| --- | --- | --- |
| 제목 | Title |  |
| 프로젝트 | Relation → Projects |  |
| 상태 | Status | 할 일 / 진행 / 완료 |
| 우선순위 | Select | P1 / P2 / P3 |
| 예상 시간 | Number (h) | 비어 있으면 에이전트가 추정하고 확인받음 |
| 남은 시간 | Number (h) | 부분 완료 시 갱신. 비어 있으면 예상 시간을 쓴다 |
| 마감 | Date (시각 포함) |  |
| 블록 | Text | 배치된 Calendar 이벤트 ID 목록 |

**Jobs** (지원 관리)

| 속성 | 타입 | 비고 |
| --- | --- | --- |
| 회사 | Title |  |
| 직무 | Text |  |
| 링크 | URL | 중복 저장 방지 키 |
| 마감 | Date (시각 포함) | "마감" 캘린더에도 반영 |
| 상태 | Status | 관심 / 지원 / 서류 / 면접 / 결과 |

**동기화 원칙**

- 할 일의 내용(제목, 상태, 마감)은 Notion에서만 수정한다.
- 시간 블록은 Calendar에만 있다. Notion "블록" 칸에는 이벤트 ID만 남긴다.
- 에이전트가 만든 Calendar 이벤트에는 `extendedProperties.private`에 `task_id`, `plan_id`, `kind`(task / routine / deadline / project)를 넣는다. 중복 판단과 복구는 이 값을 기준으로 하고, Notion "블록" 칸은 사람이 보기 위한 사본이다.
- 양방향 자동 동기화는 만들지 않는다. 완료는 Discord에서 말하면 에이전트가 Notion 상태를 바꾼다.
- Notion integration 토큰은 이 세 DB에만 공유한다.

## Google Calendar 구성

캘린더를 용도별로 네 개 둔다. "고정" 캘린더는 사람이 관리하고, 에이전트는 승인받은 일정을 추가만 한다.

| 캘린더 | 쓰는 쪽 | 내용 |
| --- | --- | --- |
| 고정 | 사람 (에이전트는 승인 후 추가만) | 수업, 약속, 면접. 반복 일정(RRULE) 사용 |
| 계획 | 에이전트 | Task 블록, 루틴 블록 |
| 프로젝트 | 에이전트 | Projects의 단계별 기간 (종일 막대, 간트 차트처럼 표시) |
| 마감 | 에이전트 | 시각이 있는 마감 (Task, 채용 공고) |

- Calendar API는 planner MCP만 호출한다. Hermes 기본 Google Workspace 스킬은 설치하지 않는다. 이 스킬은 Gmail·Drive를 포함한 전체 범위를 요청하고, 설치하면 LLM이 승인 흐름을 거치지 않고 캘린더에 쓸 수 있다.
- OAuth 범위는 `calendar.events` 하나다. 캘린더 네 개는 사람이 직접 만들고, ID는 `planner.yaml`에 적는다.
- OAuth 동의 화면은 게시 상태를 "프로덕션"으로 둔다. "테스트" 상태에서는 refresh token이 7일 뒤 만료된다. 미인증 앱 경고는 본인만 쓰므로 무시한다.
- 최초 인증은 데스크톱에서 planner의 인증 스크립트로 한 번 하고, 만든 토큰 파일을 서버 `~/assistant-data/planner/`로 복사한다.
- 폰에서는 Google Calendar 앱으로 타임라인과 알림을, Notion Calendar 앱으로 Notion 마감을 함께 확인한다.

## 플래너 규칙 파일

수면·식사·집중 시간·루틴은 Hermes 메모리가 아니라 `planner.yaml`에 둔다. 메모리는 글자 수 제한이 작아 규칙이 밀려날 수 있기 때문이다.

```yaml
timezone: Asia/Seoul
calendars:                 # Google Calendar ID
  fixed: "...@group.calendar.google.com"
  plan: "..."
  project: "..."
  deadline: "..."
day: { start: "08:30", end: "01:00" }   # end가 start보다 이르면 다음 날 시각
blocked:
  - { name: 점심, time: "12:00-13:00" }
  - { name: 저녁, time: "18:30-19:30" }
focus_hours: ["09:30-12:00", "20:00-23:00"]  # P1 작업을 우선 배치
block: { min: 30m, max: 120m, buffer: 15m }
slack_ratio: 0.2   # 하루 빈 시간의 20%는 비워 둠
routines:
  - { name: Java 공부, duration: 60m, frequency: daily, prefer: evening }
  - { name: 운동, duration: 90m, frequency: 3/week }
auto_apply:        # 자동 반영 기준 (아래 참고)
  max_changed_blocks: 2
  same_day_only: true
```

- **시간이 정해진 반복**(수업, 정기 회의)은 "고정" 캘린더의 반복 일정으로 만든다.
- **시간이 유동적인 반복**(매일 Java 1시간, 주 3회 운동)은 `routines`에 적고, 계획을 짤 때마다 블록을 새로 배치한다. 주 단위 횟수는 이번 주(월요일 시작) "계획" 캘린더에 있는 같은 루틴 블록을 세어 계산한다. 별도 데이터는 쌓지 않는다.
- 수치는 예시이며 1\~2주 써 본 뒤 조정한다.

## MCP 서버와 도구

MCP는 planner와 jobs 두 개를 Python(FastMCP, stdio)으로 만들고 Hermes 컨테이너 안에서 실행한다. 각 MCP는 독립된 uv 프로젝트로 두고, 서버 진입점은 한 파일로, 배치 알고리즘처럼 테스트가 필요한 로직은 별도 모듈로 나눈다.

**planner MCP** (Notion API + Google Calendar API)

| 도구 | 역할 |
| --- | --- |
| `list_tasks` / `add_task` / `update_task` / `complete_task` | Notion Tasks CRUD |
| `get_day(date)` | 고정 일정과 계획 블록을 합친 하루 타임라인 |
| `find_free_slots(from, to)` | 규칙과 고정 일정을 뺀 빈 시간 |
| `propose_plan(from, to)` | 배치 초안을 SQLite에 저장하고 `plan_id` 반환. Calendar에는 쓰지 않음 |
| `apply_plan(plan_id)` | 초안을 Calendar에 쓰고 Notion "블록" 칸 갱신 |
| `reschedule(reason, from)` | 변경 이후 계획 블록만 다시 배치한 초안 생성. 자동 반영 가능 여부를 함께 반환 |
| `revert_plan(plan_id)` | 반영한 초안을 되돌림 (자동 반영 취소용) |
| `add_event(...)` | 고정 일정 추가 (승인 후) |

**배치 알고리즘** (코드로 처리)

1. 빈 시간 = 하루 범위 − 고정 일정 − `blocked` − 블록 사이 여유 − `slack_ratio`
2. 루틴을 선호 시간대에 먼저 배치한다.
3. Task를 (마감까지 남은 여유 시간, 우선순위) 순으로 정렬해 배치한다. 필요한 시간은 남은 시간, 없으면 예상 시간이다. `block.max`를 넘으면 나눈다.
4. P1은 `focus_hours`부터 채운다.
5. 마감 전에 다 배치할 수 없으면 초안에 "시간 부족"으로 표시한다. 수면 시간을 임의로 줄이지 않는다.

**초안 규칙**

- `apply_plan`은 쓰기 전에 현재 Calendar와 다시 비교하고, 초안 이후 고정 일정이 바뀌어 겹치면 반영하지 않고 재생성을 요청한다.
- 초안은 대상 기간이 시작되면 만료된다.
- 모든 시각은 `Asia/Seoul` 기준 timezone-aware 값으로 다루고, 자정을 넘는 하루(08:30\~01:00)를 하나의 날로 계산한다.

LLM은 자연어 해석, 소요 시간 추정, 우선순위 판단, 초안 설명만 맡는다.

### 자동 반영 기준

`reschedule` 결과가 아래를 모두 만족하면 코드가 `auto_apply: true`를 반환하고, 에이전트는 승인 없이 반영한 뒤 바뀐 내용과 함께 "되돌리려면 '취소'"라고 알린다.

- "계획" 캘린더의 블록만 바뀐다. 고정·프로젝트·마감 캘린더는 건드리지 않는다.
- 바뀌는 블록이 `auto_apply.max_changed_blocks`개 이하이고, 모두 같은 날 안에서 움직인다.
- "시간 부족" 상태가 새로 생기지 않는다.

다음은 항상 승인을 받는다: 전날 밤·주간 계획 초안, 고정 일정 추가, 에이전트가 추정한 소요 시간.

**jobs MCP**

| 도구 | 역할 |
| --- | --- |
| `collect(sources, keywords)` | 사이트별 수집. 공식 API → fetch → Camofox 순으로 시도 |
| `new_since_last()` | SQLite에 없는 새 공고만 반환 (중복 제거는 코드로) |
| `save_to_notion(job_id)` | 관심 공고를 Notion Jobs에 저장하고 마감을 "마감" 캘린더에 추가 |

- 브라우저(Camofox)는 일반 fetch가 막히는 사이트에만 쓴다. jobs MCP가 `http://camofox:9377` REST API를 직접 호출하므로 Hermes Camofox 플러그인은 설치하지 않는다.
- 로그인이 필요한 사이트(LinkedIn 등)는 본 계정으로 자동화하지 않는다.
- `save_to_notion`은 Discord 대화(GPT)에서만 호출한다. 수집 cron에는 노출하지 않는다.

## 주요 시나리오와 cron

- **할 일 추가**: "DB 프로젝트 ERD 정리, 2시간, 금요일까지" → `add_task` → "이번 주 계획에 넣을까?"
- **전날 밤 계획**: cron → `propose_plan(내일)` → 타임라인 전송 → "OK"면 `apply_plan`
- **변경 발생**: "3시에 회의 생겼어" → 고정 일정 추가 확인 → `reschedule` → 자동 반영 기준에 맞으면 반영 후 알림, 아니면 바뀌는 부분만 보여주고 승인
- **완료 / 부분 완료**: "ERD 끝" → `complete_task`. "절반 했어" → 남은 시간 갱신 후 재배치 대상
- **채용 공고**: 새 공고 알림 → "이거 저장" → Notion Jobs + 마감 캘린더

| 시각 | 작업 | 모델 | 허용 도구 |
| --- | --- | --- | --- |
| 매일 22:30 | 내일 계획 초안 | GPT | planner |
| 매일 08:00 | 오늘 타임라인 요약. 미승인 초안이 있으면 반영 여부를 다시 물음 | GPT | planner |
| 일요일 20:00 | 주간 계획 + 마감 위험 목록 | GPT 상위 모델 | planner |
| 매일 09:00, 18:00 | 채용 공고 수집 → 새 공고만 알림 | K-EXAONE | jobs (`collect`, `new_since_last`) |
| 키 만료 5일 전 | EXAONE API 키 교체 알림 | GPT 경량 모델 | 없음 |

- cron은 게이트웨이가 60초마다 확인해 실행하므로 게이트웨이가 항상 떠 있어야 한다.
- 각 cron 작업은 `enabled_toolsets`로 필요한 도구만 연다. 공고 페이지에 섞인 지시문이 일정이나 Notion을 건드리지 못하게 하기 위해서다.

## 메모리

Hermes 기본 메모리로 시작하고, 부족할 때만 외부 제공자를 붙인다.

| 계층 | 내용 | 비고 |
| --- | --- | --- |
| MEMORY.md / USER.md | 매 세션에 주입되는 핵심 정보 | 각 2,200자 / 1,375자 제한 |
| 세션 검색 | 모든 대화를 SQLite FTS5로 검색 | 에이전트가 필요할 때 호출 |
| 외부 제공자 (선택) | Honcho, Mem0 등 (플러그인 설치) | 한 번에 하나만 활성화 |

- Hermes는 스스로 판단할 때만 메모리에 기록한다. 꼭 남길 내용은 "기억해"라고 명시한다.
- 규칙성 정보(루틴, 수면 시간)는 메모리가 아니라 `planner.yaml`에 둔다.
- Honcho는 자체 호스팅이 가능하지만 Postgres와 별도 LLM 호출이 필요하다. 필요해지면 클라우드 버전부터 검토한다. 외부 제공자도 개인 데이터 원칙을 따른다.

## 저장소와 배포

문서, MCP 코드, 배포 설정을 이 저장소(`assistant`) 하나에 둔다.

```
assistant/
├─ CLAUDE.md
├─ docs/
├─ mcp/
│  ├─ planner/        # uv 프로젝트: server.py, scheduling 모듈, tests/
│  └─ jobs/
└─ deploy/
   ├─ compose.yaml    # hermes, camofox
   ├─ Dockerfile      # FROM nousresearch/hermes-agent + mcp/
   ├─ .env.example
   ├─ hermes/config.yaml   # 기준 설정. 서버 ~/assistant-data/로 복사해 쓴다
   └─ planner.yaml.example
```

**서버**

| 항목 | 값 |
| --- | --- |
| CPU | Intel Core i5-7200U (2코어 4스레드, x86_64) |
| 메모리 | 12GB |
| OS | Ubuntu Server |
| 실행 방식 | Docker Compose. 이미지는 이 서버에서 직접 빌드한다 |

- 서버가 `linux/amd64`이므로 빌드와 실행 아키텍처가 같다. 다른 기기에서 빌드하거나 레지스트리에 올리지 않는다.
- 메모리는 hermes와 camofox만 고려한다. camofox는 `mem_limit: 2g`로 시작하고, 실제 사용량을 보고 조정한다. LLM은 모두 외부 API이므로 서버에서 모델을 돌리지 않는다.
- CPU가 2코어이므로 빌드는 의존성 레이어를 캐시해 다시 빌드할 때 `mcp/` 코드 레이어만 바뀌게 한다.

서버에는 이 저장소를 clone해 두고, 상태 디렉터리는 저장소 밖에 둔다. `git clean` 같은 저장소 작업이 토큰을 지우지 않게 하기 위해서다. Hermes 공식 이미지는 모든 상태를 `/opt/data` 하나에 두므로 이 디렉터리를 그대로 마운트한다.

```
~/assistant/                # 이 저장소 (git clone)
└─ deploy/
   ├─ compose.yaml          # build: hermes 이미지, data 경로는 .env로 지정
   └─ .env                  # compose 변수 (DATA_DIR 등), 커밋 안 함
~/assistant-data/           # → hermes:/opt/data
   ├─ config.yaml     # Hermes가 부팅 시 마이그레이션하며 고쳐 쓸 수 있음
   ├─ .env            # Discord, Notion, EXAONE 키
   ├─ auth.json       # openai-codex 토큰
   ├─ planner/        # planner.yaml, google_token.json, plans.sqlite
   └─ jobs/           # jobs.sqlite
```

| 컨테이너 | 내용 | 설정 |
| --- | --- | --- |
| hermes | 게이트웨이, cron, planner·jobs MCP | `build: deploy/Dockerfile`, `restart: unless-stopped`, `~/assistant-data` → `/opt/data`, `TZ`·`HERMES_TIMEZONE=Asia/Seoul`, `mem_limit: 3g` |
| camofox | 안티디텍션 브라우저 (`ghcr.io/jo-inc/camofox-browser`, 버전 고정) | `mem_limit` 설정, 외부 포트 노출 없음 |

**이미지 빌드와 배포**

- `deploy/Dockerfile`은 공식 이미지(`nousresearch/hermes-agent`, 버전 태그 고정) 위에 `mcp/`와 의존성을 얹는다. 공식 이미지의 `uv`는 PATH에 없으므로 `ghcr.io/astral-sh/uv`에서 같은 버전을 복사해 `/usr/local/bin`에 둔다.
- Hermes 버전은 Dockerfile 한 곳에만 적는다. 버전을 올리는 것도 커밋이다.
- 서버 설치와 실행 절차는 [setup/01-base.md](setup/01-base.md)에 있다.
- 빌드와 배포는 모두 서버에서 한다: `cd ~/assistant && git pull && docker compose -f deploy/compose.yaml up -d --build`.
- 평소에는 데스크톱에서 `deploy/deploy.sh`로 배포한다. Tailscale SSH로 서버에 접속해 위 명령을 실행하므로 GitHub에 push한 `main`만 배포된다.
- GitHub Actions는 배포에 쓰지 않고 CI(테스트)에만 쓴다. 서버는 Tailscale 안에만 있으므로 GitHub에 tailnet 키나 서버 SSH 키를 맡기지 않는다.
- 공식 이미지 버전을 올릴 때는 Dockerfile의 태그를 바꿔 커밋하고 같은 명령으로 다시 빌드한다. 문제가 생기면 이전 커밋으로 되돌려 다시 빌드한다.
- 초기에는 `mcp/`를 컨테이너에 bind mount해 서버에서 바로 고치며 만들고, 안정화되면 bind mount를 빼고 이미지에 포함한다.
- `config.yaml`은 Hermes가 고쳐 쓸 수 있으므로 저장소의 파일은 기준본으로 두고, 서버 쪽과 달라지면 차이를 확인해 저장소에 반영한다.

**보안**

- Discord 허용 사용자(`DISCORD_ALLOWED_USERS`)는 본인 ID 하나. 봇에는 Message Content Intent만 켠다.
- Discord 플랫폼 도구는 `platform_toolsets.discord`로 planner·jobs MCP, 메모리, 세션 검색만 연다. 터미널, 파일, 코드 실행은 끈다.
- Google OAuth는 `calendar.events`만, Notion 토큰은 세 DB에만 공유.
- stdio MCP에는 PATH, HOME 등 일부를 빼고 환경 변수가 전달되지 않으므로 필요한 키만 `env` 블록에 명시한다.
- 서버 외부 접근은 Tailscale로만 한다.
- `~/assistant-data/`에는 토큰이 모두 들어 있으므로 백업은 암호화해 서버 밖에 둔다.

## 구현 순서

일정 관리를 먼저 완성하고, 채용 공고는 그 다음에 붙인다. 단계마다 브랜치를 따로 만들고, 끝나면 여기 체크한다.

- [x] **기반**: Ubuntu Server, Tailscale, Docker 설치 → Hermes 컨테이너 실행 ([절차](setup/01-base.md)) — 2026-11-19 완료
- [ ] **모델**: `openai-codex` 로그인, K-EXAONE 키 발급(학습 opt-out 먼저)·`providers.exaone` 등록, `auxiliary.compression` 지정
- [ ] **Discord**: 봇 생성(Message Content Intent), 게이트웨이 연결, 허용 사용자·`platform_toolsets` 제한
- [ ] **Notion**: Projects·Tasks·Jobs DB 생성, integration 토큰 발급·공유
- [ ] **Google**: Cloud 프로젝트, Calendar API, OAuth 클라이언트(데스크톱 앱, 프로덕션 게시), 캘린더 4개 생성, 토큰 발급
- [ ] **planner MCP v1**: `list/add/update/complete_task`, `get_day`, `find_free_slots`, GitHub Actions CI(pytest)
- [ ] **planner MCP v2**: `propose_plan`, `apply_plan`, 22:30·08:00 cron
- [ ] **planner MCP v3**: `reschedule`, `revert_plan`, 자동 반영, 주간 계획 cron
- [ ] **jobs MCP**: 수집·중복 제거·알림, Camofox 컨테이너 추가, 키 만료 알림 cron
- [ ] **고정**: bind mount 제거, Dockerfile로 `mcp/` 포함한 이미지 빌드, 1\~2주 사용 후 `planner.yaml`·자동 반영 기준 조정

## 미결정 사항

| 항목 | 정할 시점 |
| --- | --- |
| `planner.yaml` 실제 값: 수면·식사·집중 시간대, 루틴 목록 | planner MCP v2 전 (초기값), 2주 사용 후 조정 |
| 채용 공고 소스: 대상 사이트와 키워드, 공식 API 제공 여부 | jobs MCP 전 |
| K-EXAONE 도구 호출 안정성: 실제 테스트 후 cron에 계속 쓸지 | jobs MCP 단계에서 테스트 |
| 컨텍스트 압축에 쓸 GPT 경량 모델 ID | 모델 단계 (`openai-codex` 모델 목록 확인 후) |

## 결정 기록

| 날짜 | 결정 | 이유 |
| --- | --- | --- |
| 2026-11-19 | Notion은 planner MCP가 직접 API로 호출하고 공식 Notion MCP는 붙이지 않는다 | 모든 쓰기가 승인 흐름 안에 있고 토큰 범위가 좁다 |
| 2026-11-19 | Google Calendar는 planner MCP가 단독으로 다루고 Workspace 스킬은 쓰지 않는다 | 스킬은 전체 범위를 요청하고 승인 없이 쓸 수 있다 |
| 2026-11-19 | 작은 재배치는 자동 반영 후 알린다 (기준은 위 자동 반영 기준) | 매번 승인은 번거롭다. 큰 변경과 새 계획은 계속 승인 |
| 2026-11-19 | K-EXAONE은 채용 공고에만 쓰고, 압축은 GPT로 옮긴다 | 입출력이 학습에 쓰이는 약관이라 개인 데이터를 보내지 않는다 |
| 2026-11-19 | 문서·MCP·배포를 이 저장소 하나에 둔다 (`homeserver-mcp` 분리 안 함) | 문서와 코드가 함께 바뀐다 |
| 2026-11-19 | Hermes 상태는 `/opt/data` 단일 마운트, `auxiliary.web_extract` 삭제 | 공식 이미지 구조와 설정 키 확인 결과 |
| 2026-11-19 | 이미지는 홈서버(x86_64)에서 직접 빌드하고, 레지스트리(GHCR)는 쓰지 않는다 | 서버 하나뿐이고 빌드·실행 아키텍처가 같다 |
| 2026-11-19 | 배포는 데스크톱에서 `deploy/deploy.sh`로 수동 실행하고, GitHub Actions는 CI에만 쓴다 | 서버가 Tailscale 안에만 있다. 자동 배포를 하려면 tailnet·SSH 키를 GitHub에 맡기거나 서버에 runner를 둬야 하는데, 배포가 그만큼 잦지 않다 |
| 2026-11-19 | 상태 디렉터리 `~/assistant-data`를 저장소 밖에 둔다 | 저장소 작업이 토큰을 지우지 않게 한다 |
