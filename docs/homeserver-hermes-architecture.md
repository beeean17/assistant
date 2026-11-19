# 홈서버 Hermes 개인 비서 설계

Nov 19, 2026 · @성빈 · 최종 수정 Nov 20, 2026

## 개요

홈서버에 Hermes Agent를 Docker로 띄우고, 기능별 MCP를 붙여 Discord로 대화하는 개인 비서를 만든다. 일정의 원본과 알림은 Google Calendar, 할 일의 원본은 Notion이 맡고, Hermes는 둘을 잇는다.

**핵심 기능**

- **미래 일정 관리**: 고정 일정 사이 빈 시간에 할 일과 루틴을 시간 블록으로 배치하고, 변경이 생기면 다시 배치한다.
- **프로젝트 관리**: 프로젝트를 단계와 할 일로 나누고, 단계 기간을 캘린더 막대로 보여주며, 마감 전에 시간이 모자라는 단계를 미리 알린다.
- **채용 공고 알림**: 금융권 IT·데이터·핀테크 공고를 주기적으로 수집해 새 공고만 Discord로 알린다.
- **대화 기억**: 가끔 나누는 대화에서 중요한 내용을 기억하고, 과거 대화를 검색한다.

**범위 밖**: 코딩 작업, 실제 행동 기록(트래킹).

**원칙**

- 시간 계산과 중복 판단은 코드가, 자연어 해석과 판단은 LLM이 맡는다.
- 에이전트가 만든 변경(계획 초안, 해석한 일정, 추정한 소요 시간)은 Discord에서 승인받은 뒤 반영한다. 단, [자동 반영 기준](#자동-반영-기준)에 맞는 작은 재배치는 반영 후 알린다.
- 사용자가 직접 지시한 쓰기("ERD 끝", "이거 저장")는 그 지시를 승인으로 본다.
- 개인 데이터(일정, 할 일, 대화)는 학습에 쓰이는 외부 API로 보내지 않는다. 예외로 K-EXAONE을 GPT가 실패할 때 fallback으로 쓴다. 계정의 학습 활용 동의 설정은 아직 확인하지 못했으므로, 확인 전까지 fallback으로 넘어간 대화는 학습에 쓰일 수 있다.
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
        └─► K-EXAONE API: 채용 공고 수집·요약, GPT 실패 시 fallback
```

Discord가 유일한 입력 창구다. 시간은 Google Calendar, 할 일은 Notion이 원본이고, Hermes는 MCP로 둘을 읽고 쓴다. Calendar와 Notion에 접근하는 자격 증명은 planner MCP만 가진다.

## 모델 배분

대화와 판단, 개인 데이터를 다루는 작업은 모두 ChatGPT 구독(OAuth)으로 처리한다. K-EXAONE은 공개 데이터인 채용 공고와, GPT가 실패할 때의 fallback에만 쓴다. Claude API는 쓰지 않는다.

| 작업 | 모델 | 지정 방법 |
| --- | --- | --- |
| Discord 대화, 일정 조정, 매일 cron | GPT 메인: `gpt-6.2-sol` (ChatGPT Plus, `openai-codex`) | `model.default` |
| 주간 계획 | GPT 상위: `gpt-6.2-astra` | cron 작업별 `--model` |
| 컨텍스트 압축, 키 만료 알림 | GPT 경량: `gpt-6-luna` | `auxiliary.compression`, cron 작업별 `--model` |
| 채용 공고 수집·요약 | K-EXAONE 2.5 | cron 작업별 `--model --provider` |
| GPT 실패 시 (한도 초과 429, 서버 오류 5xx, 인증 실패 401/403) | K-EXAONE 2.5 | `fallback_providers` |

**연결**

- GPT: `hermes auth add openai-codex`로 기기 코드 로그인. `auth.adopt_external_logins: false`로 Codex CLI 토큰을 가져오지 않게 한다.
- K-EXAONE: `providers.exaone`으로 등록하고 `fallback_providers`에 넣는다. base URL `https://api.exaone.ai/v1`, 모델 ID `k-exaone_v2.5`, 키는 `EXAONE_API_KEY`. 형식은 [hermes-notes.md](hermes-notes.md) 참고.
- K-EXAONE 공식 예시는 `agent.reasoning_effort`를 전역으로 바꾸지만, 그러면 GPT에도 적용되므로 따르지 않는다. 추론 강도는 jobs 단계에서 cron 작업별로 정한다.
- `-900k` 모델 변형은 쓰지 않는다. Codex 경로의 272K 창으로 충분하고 한도만 더 쓴다.
- 위 설정은 `deploy/hermes/configure.sh`가 적용한다(아래 "저장소와 배포").
- cron 모델 결정 순서: 작업별 지정 → `cron.model` → 메인 모델. 작업별로 고정한 모델은 `fallback_providers`를 쓰지 않는다.
- 웹 추출은 LLM을 쓰지 않으므로 모델을 따로 지정하지 않는다.

**주의**

- ChatGPT 구독 사용량은 Codex·Work 한도에서 차감된다. 보조 작업은 기본값(`auto`)이면 메인 모델로 처리되므로 압축은 경량 모델로 따로 지정한다.
- Codex CLI와 Hermes는 각자 로그인한다. refresh token을 복사해 공유하면 한쪽이 401로 끊긴다.
- Codex 토큰 갱신이 실패하면 Hermes가 토큰을 격리하고, 다시 로그인하기 전까지 cron이 멈춘다. 08:00 요약이 오지 않으면 이것부터 확인한다.
- K-EXAONE 약관: 비상업 용도만 허용되고, API 키는 30일마다 만료된다. 학습 활용은 출처마다 설명이 다르다. 처음 확인한 약관 요약은 "기본으로 쓰이고 opt-out은 소급되지 않음", 공식 Rate Limits 문서는 "(선택) 동의" 항목(마이 프로필 > 동의 및 알림 관리)으로 설명한다. 계정 설정 화면의 값이 기준이다.
  - 키를 처음 발급할 때 학습 opt-out을 먼저 적용한다.
  - 만료 5일 전 Discord 알림을 cron으로 둔다. 키가 만료되면 fallback이 조용히 깨지므로 이 cron에서 `hermes fallback check --live`도 돌린다.
  - 현재 키: 2026-11-20 발급, 2026-12-20 만료 예정.
  - `reasoning_effort`는 기본값이 `max`이므로 수집 작업에는 `low`로 명시한다.
- `delegate_task`는 호출마다 모델을 지정할 수 없다(의도된 동작). 위임은 쓰지 않는다.
- K-EXAONE의 도구 호출이 불안정하면 해당 작업만 GPT 경량 모델로 옮긴다.
- fallback은 턴 단위다. 다음 메시지부터 GPT를 다시 시도하되, Codex 주간 한도처럼 리셋 시각이 알려진 실패는 리셋까지 K-EXAONE을 계속 쓴다. 전환될 때 Discord에 알림이 뜬다.
- 모델을 고정한 cron(주간 계획 `gpt-6.2-astra` 등)은 fallback을 타지 않는다. 모델을 지정하지 않은 cron은 탄다.

## Notion 스키마

Notion은 프로젝트와 할 일의 원본이다. 반복은 Notion에 만들지 않고 규칙 파일과 Calendar 반복 일정으로 처리한다.

**Projects**

| 속성 | 타입 | 비고 |
| --- | --- | --- |
| 이름 | Title |  |
| 분류 | Select | 수업 / 개인 / 취업 / 동아리 |
| 기간 | Date (범위) | 단계가 없으면 "프로젝트" 캘린더에 막대 하나로 반영 |
| 상태 | Status | 진행 / 보류 / 완료 |

**Milestones** (프로젝트의 단계)

| 속성 | 타입 | 비고 |
| --- | --- | --- |
| 이름 | Title |  |
| 프로젝트 | Relation → Projects | 필수 |
| 기간 | Date (범위) | "프로젝트" 캘린더에 막대로 반영. 프로젝트 기간 안에 있어야 한다 |
| 상태 | Status | 예정 / 진행 / 완료 |

**Tasks**

| 속성 | 타입 | 비고 |
| --- | --- | --- |
| 제목 | Title |  |
| 프로젝트 | Relation → Projects |  |
| 단계 | Relation → Milestones | 선택. 넣으면 프로젝트는 단계의 프로젝트로 코드가 채운다 |
| 상태 | Status | 할 일 / 진행 / 완료 |
| 우선순위 | Select | P1 / P2 / P3 |
| 예상 시간 | Number (h) | 비어 있으면 에이전트가 추정하고 확인받음 |
| 남은 시간 | Number (h) | 부분 완료 시 갱신. 비어 있으면 예상 시간을 쓴다 |
| 마감 | Date (시각 포함) | 비어 있으면 단계 종료일, 단계도 없으면 프로젝트 종료일을 마감으로 쓴다 |
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

- 할 일의 내용(제목, 상태, 마감)은 Notion에서만 수정한다. 프로젝트와 단계의 내용(이름, 기간, 상태)도 같다.
- 시간 블록은 Calendar에만 있다. Notion "블록" 칸에는 이벤트 ID만 남긴다.
- 에이전트가 만든 Calendar 이벤트에는 `extendedProperties.private`에 `task_id`, `plan_id`, `kind`(task / routine / deadline / project)를 넣는다. 중복 판단과 복구는 이 값을 기준으로 하고, Notion "블록" 칸은 사람이 보기 위한 사본이다.
- 프로젝트 막대(`kind: project`)에는 `task_id`, `plan_id` 대신 `project_id`를 넣고, 단계 막대면 `milestone_id`도 넣는다.
- "프로젝트" 캘린더는 Notion Projects·Milestones의 사본이다. 막대를 Calendar에서 직접 옮겨도 다음 동기화 때 Notion 값으로 돌아간다.
- 양방향 자동 동기화는 만들지 않는다. 완료는 Discord에서 말하면 에이전트가 Notion 상태를 바꾼다.
- Notion integration 토큰은 이 네 DB에만 공유한다. DB는 "비서" 페이지 아래에 있고, integration은 그 페이지에만 연결한다. 데이터 소스 ID와 Status 그룹은 [setup/02-notion.md](setup/02-notion.md)에 있다.
- 양방향 관계라서 Projects에 `단계`·`할 일`, Milestones에 `할 일` 역방향 속성이 있다. Notion이 관리하므로 코드는 쓰지 않는다.
- 코드는 Status를 옵션 이름이 아니라 그룹(to_do / in_progress / complete)으로 판단한다.

## Google Calendar 구성

캘린더를 용도별로 네 개 둔다. "고정" 캘린더는 사람이 관리하고, 에이전트는 승인받은 일정을 추가만 한다.

| 캘린더 | 쓰는 쪽 | 내용 |
| --- | --- | --- |
| 고정 | 사람 (에이전트는 승인 후 추가만) | 수업, 약속, 면접. 반복 일정(RRULE) 사용 |
| 계획 | 에이전트 | Task 블록, 루틴 블록 |
| 프로젝트 | 에이전트 | Milestones의 단계별 기간. 단계가 없는 프로젝트는 프로젝트 기간 (종일 막대, 간트 차트처럼 표시) |
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
project:           # 프로젝트 점검 (아래 참고)
  horizon: 8w      # 모의 배치 범위
  risk_days: 2     # 예상 완료일이 마감 전 이 일수 안이면 "빠듯"
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
| `list_projects` / `add_project` / `update_project` | Notion Projects CRUD |
| `add_milestone` / `update_milestone` | Notion Milestones 추가·수정. 기간이 프로젝트 기간 안인지 코드가 확인 |
| `sync_project_calendar()` | "프로젝트" 캘린더 막대를 Notion Projects·Milestones에 맞추고 바뀐 막대를 반환 |
| `project_status(project?)` | 모의 배치로 단계별 남은 시간, 부족 시간, 예상 완료일, 판정을 반환. Calendar에는 쓰지 않음 |
| `propose_breakdown(project, milestones, tasks)` | 단계·할 일 초안을 SQLite에 저장하고 `breakdown_id`와 점검 결과 반환. Notion에는 쓰지 않음 |
| `apply_breakdown(breakdown_id)` | 초안을 Notion에 만들고 "프로젝트" 캘린더를 맞춤 |

**배치 알고리즘** (코드로 처리)

1. 빈 시간 = 하루 범위 − 고정 일정 − `blocked` − 블록 사이 여유 − `slack_ratio`
2. 루틴을 선호 시간대에 먼저 배치한다.
3. Task를 (마감까지 남은 여유 시간, 우선순위) 순으로 정렬해 배치한다. 마감이 없는 Task는 소속 단계의 종료일, 단계도 없으면 프로젝트 종료일을 마감으로 쓴다. 필요한 시간은 남은 시간, 없으면 예상 시간이다. `block.max`를 넘으면 나눈다.
4. P1은 `focus_hours`부터 채운다.
5. 마감 전에 다 배치할 수 없으면 초안에 "시간 부족"으로 표시한다. 수면 시간을 임의로 줄이지 않는다.

**초안 규칙**

- `apply_plan`은 쓰기 전에 현재 Calendar와 다시 비교하고, 초안 이후 고정 일정이 바뀌어 겹치면 반영하지 않고 재생성을 요청한다.
- 초안은 대상 기간이 시작되면 만료된다.
- 모든 시각은 `Asia/Seoul` 기준 timezone-aware 값으로 다루고, 자정을 넘는 하루(08:30\~01:00)를 하나의 날로 계산한다.

LLM은 자연어 해석, 소요 시간 추정, 우선순위 판단, 프로젝트 분해 초안 작성, 초안 설명만 맡는다.

### 자동 반영 기준

`reschedule` 결과가 아래를 모두 만족하면 코드가 `auto_apply: true`를 반환하고, 에이전트는 승인 없이 반영한 뒤 바뀐 내용과 함께 "되돌리려면 '취소'"라고 알린다.

- "계획" 캘린더의 블록만 바뀐다. 고정·프로젝트·마감 캘린더는 건드리지 않는다.
- 바뀌는 블록이 `auto_apply.max_changed_blocks`개 이하이고, 모두 같은 날 안에서 움직인다.
- "시간 부족" 상태가 새로 생기지 않는다.

다음은 항상 승인을 받는다: 전날 밤·주간 계획 초안, 고정 일정 추가, 에이전트가 추정한 소요 시간, 프로젝트 분해 초안.

### 프로젝트 캘린더 동기화

`sync_project_calendar`는 "프로젝트" 캘린더를 Notion에 맞춘다. 여러 번 실행해도 결과가 같다.

- 대상은 상태가 완료가 아닌 프로젝트다. 완료된 프로젝트의 막대는 남겨 두고 더 고치지 않는다.
- 단계가 하나라도 있으면 단계마다 막대를 만들고, 없으면 프로젝트 기간으로 막대 하나를 만든다. 제목은 "프로젝트 · 단계"다.
- 막대는 `project_id`, `milestone_id`로 찾는다. 있으면 기간과 제목을 고치고, Notion에서 사라진 단계의 막대는 지운다.
- 프로젝트·단계를 쓰는 도구(`add_project`, `update_project`, `add_milestone`, `update_milestone`, `apply_breakdown`)가 끝에 실행한다. Notion에서 직접 고친 기간은 08:00 cron이 맞춘다.
- 승인 없이 반영하고 바뀐 막대를 알린다. 사용자가 Notion에 적었거나 승인한 값을 옮기는 것이기 때문이다.

### 프로젝트 점검

`project_status`는 배치 알고리즘을 Calendar에 쓰지 않고 지금부터 `project.horizon`까지 돌려(모의 배치) 단계마다 다음을 반환한다.

| 값 | 내용 |
| --- | --- |
| 남은 시간 | 완료되지 않은 Task의 남은 시간 합계. 없으면 예상 시간을 쓴다 |
| 부족 시간 | 마감 전에 배치하지 못한 시간 |
| 예상 완료일 | 마지막 블록이 놓인 날 |
| 미추정 Task 수 | 예상 시간이 없어 계산에서 빠진 Task의 수 |
| 판정 | 부족(부족 시간이 있음) / 빠듯(다 배치되지만 예상 완료일이 마감 전 `project.risk_days`일 안) / 여유 |

- 모든 프로젝트의 Task와 루틴을 함께 배치한다. 빈 시간은 프로젝트끼리 나눠 쓰므로 프로젝트 하나만 따로 계산하면 실제보다 여유 있게 나온다.
- "계획" 캘린더에 이미 있는 블록은 무시하고 남은 시간 전체를 다시 놓는다.
- 단계에 속하지 않은 Task는 프로젝트 단위로 묶어 같은 값을 반환한다.
- 수치와 판정은 코드가 정한다. LLM은 결과를 설명하고 대안(단계 기간 조정, 할 일 줄이기)을 제안한다. 대안을 반영하려면 승인을 받는다.

### 프로젝트 분해

1. 사용자가 프로젝트와 기한을 말한다.
2. LLM이 단계, 할 일, 예상 시간 초안을 만든다.
3. `propose_breakdown`이 초안을 검증해 저장하고, 초안을 포함한 모의 배치 결과를 함께 반환한다.
4. Discord에 초안과 점검 결과를 보여 준다. 승인하면 `apply_breakdown`이 Notion에 만든다.

- 검증은 코드가 한다: 단계 기간이 프로젝트 기간 안에 있는지, 할 일마다 예상 시간이 0보다 큰지, 같은 프로젝트에 이름이 같은 단계가 없는지.
- 초안을 고치려면 새 초안을 만든다. 초안은 `plans.sqlite`에 둔다.
- `apply_breakdown`은 Notion에만 쓰고 "프로젝트" 캘린더를 맞춘다. 시간 블록은 이후 `propose_plan`이 배치한다.
- 쓰는 도중 실패하면 만든 항목을 SQLite에 기록해 두고, 다시 실행하면 남은 항목만 만든다.

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
- **프로젝트 시작**: "DB 프로젝트 시작, 12월 10일까지" → 단계·할 일 초안 → `propose_breakdown` → 초안과 점검 결과 전송 → "OK"면 `apply_breakdown`
- **프로젝트 점검**: "DB 프로젝트 어때?" → `project_status` → 단계별 남은 시간과 판정
- **채용 공고**: 새 공고 알림 → "이거 저장" → Notion Jobs + 마감 캘린더

| 시각 | 작업 | 모델 | 허용 도구 |
| --- | --- | --- | --- |
| 매일 22:30 | 내일 계획 초안 | GPT | planner |
| 매일 08:00 | 오늘 타임라인 요약. 미승인 초안이 있으면 반영 여부를 다시 물음. "프로젝트" 캘린더 동기화 | GPT | planner |
| 일요일 20:00 | 주간 계획 + 마감 위험 목록 + 프로젝트 점검(부족·빠듯 단계) | GPT 상위 모델 | planner |
| 매일 09:00, 18:00 | 채용 공고 수집 → 새 공고만 알림 | K-EXAONE | jobs (`collect`, `new_since_last`) |
| 키 만료 5일 전 | EXAONE API 키 교체 알림 + `hermes fallback check --live` | GPT 경량 모델 | 없음 |

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
   ├─ hermes/configure.sh  # 저장소가 관리하는 Hermes 설정 (hermes config set)
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
- `config.yaml`은 2,400줄이 넘는 Hermes 소유 파일이고 부팅 때 마이그레이션되므로 저장소에 통째로 두지 않는다. 저장소가 관리하는 키만 `deploy/hermes/configure.sh`에 적고 `hermes config set`으로 적용한다. 배포 스크립트가 매번 실행하며, 값이 바뀐 경우에만 게이트웨이를 재시작한다.
- 서버에서 `config.yaml`을 손으로 고치지 않는다. 바꿀 값은 `configure.sh`에 넣어 커밋한다.

**보안**

- Discord 허용 사용자(`DISCORD_ALLOWED_USERS`)는 본인 ID 하나. 봇에는 Message Content Intent와 Server Members Intent만 켜고(공식 문서상 둘 다 필수), Public Bot은 끈다.
- Discord 플랫폼 도구는 `platform_toolsets.discord`로 planner·jobs MCP, 메모리, 세션 검색만 연다. 터미널, 파일, 코드 실행은 끈다.
- Google OAuth는 `calendar.events`만, Notion 토큰은 네 DB에만 공유.
- stdio MCP에는 PATH, HOME 등 일부를 빼고 환경 변수가 전달되지 않으므로 필요한 키만 `env` 블록에 명시한다.
- 서버 외부 접근은 Tailscale로만 한다.
- `~/assistant-data/`에는 토큰이 모두 들어 있으므로 백업은 암호화해 서버 밖에 둔다.

## 구현 순서

일정 관리를 먼저 완성하고, 채용 공고는 그 다음에 붙인다. 단계마다 브랜치를 따로 만들고, 끝나면 여기 체크한다.

- [x] **기반**: Ubuntu Server, Tailscale, Docker 설치 → Hermes 컨테이너 실행 ([절차](setup/01-base.md)) — 2026-11-19 완료
- [x] **모델**: `openai-codex` 로그인, 메인·압축 모델 지정, K-EXAONE fallback 등록(`deploy/hermes/configure.sh`) — 2026-11-20 완료
- [x] **Discord**: 봇 생성(Message Content·Server Members Intent), 게이트웨이 연결, 허용 사용자 — 2026-11-20 완료 (설정은 사용자가 직접)
- [ ] **운영 cron**: EXAONE 키 만료 알림 + `hermes fallback check --live` (2026-12-15 전)
- [ ] **Notion**: Projects·Milestones·Tasks·Jobs DB 생성(2026-11-20 완료), integration 토큰 발급·공유 ([절차](setup/02-notion.md))
- [ ] **Google**: Cloud 프로젝트, Calendar API, OAuth 클라이언트(데스크톱 앱, 프로덕션 게시), 캘린더 4개 생성, 토큰 발급
- [ ] **planner MCP v1**: `list/add/update/complete_task`, `get_day`, `find_free_slots`, GitHub Actions CI(pytest), Discord `platform_toolsets` 제한(planner MCP·메모리·세션 검색만)
- [ ] **planner MCP 프로젝트 v1**: `list/add/update_project`, `add/update_milestone`, `sync_project_calendar`, Task의 단계 연결
- [ ] **planner MCP v2**: `propose_plan`, `apply_plan`, 22:30·08:00 cron
- [ ] **planner MCP v3**: `reschedule`, `revert_plan`, 자동 반영, 주간 계획 cron
- [ ] **planner MCP 프로젝트 v2**: `project_status`(모의 배치), 주간 계획 cron에 프로젝트 점검 추가
- [ ] **planner MCP 프로젝트 v3**: `propose_breakdown`, `apply_breakdown`
- [ ] **jobs MCP**: 수집·중복 제거·알림, Camofox 컨테이너 추가
- [ ] **고정**: bind mount 제거, Dockerfile로 `mcp/` 포함한 이미지 빌드, 1\~2주 사용 후 `planner.yaml`·자동 반영 기준 조정

## 미결정 사항

| 항목 | 정할 시점 |
| --- | --- |
| `planner.yaml` 실제 값: 수면·식사·집중 시간대, 루틴 목록 | planner MCP v2 전 (초기값), 2주 사용 후 조정 |
| `planner.yaml`의 `project` 값: 모의 배치 범위, "빠듯" 기준 일수 | planner MCP 프로젝트 v2 전 (초기값), 2주 사용 후 조정 |
| 채용 공고 소스: 대상 사이트와 키워드, 공식 API 제공 여부 | jobs MCP 전 |
| K-EXAONE 학습 활용 동의 설정 확인 (마이 프로필 > 동의 및 알림 관리 > "(선택) 동의: AI 모델 학습 및 서비스 개선을 위한 이용 기록 분석"이 꺼져 있는지) | 다음 키 교체(2026-12-20) 전 |
| K-EXAONE 도구 호출 안정성: 실제 테스트 후 cron에 계속 쓸지 | jobs MCP 단계에서 테스트 |

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
| 2026-11-19 | GPT 모델: 메인 `gpt-6.2-sol`, 주간 계획 `gpt-6.2-astra`, 압축·알림 `gpt-6-luna` | Plus 구독 한도를 Codex와 나눠 쓴다. 도구 호출이 많은 planner 흐름은 Sol, 주 1회 계획만 Astra |
| 2026-11-19 | K-EXAONE 키 발급과 provider 등록을 모델 단계에서 jobs 단계로 옮긴다 | K-EXAONE은 채용 공고에만 쓰므로 그전까지 필요 없고, 키가 30일마다 만료된다 (2026-11-20 결정으로 대체) |
| 2026-11-20 | Discord 설정은 사용자가 직접 했다. `platform_toolsets` 제한은 planner MCP v1로, 키 만료 알림 cron은 별도 "운영 cron" 항목으로 옮긴다 | 도구 제한은 MCP를 붙일 때 함께 정하는 게 자연스럽고, 키 만료(2026-12-20)는 planner 일정보다 먼저 온다 |
| 2026-11-20 | Notion DB는 Claude가 Notion 커넥터로 "비서" 페이지 아래에 만든다 | 속성 이름·옵션·관계를 문서와 정확히 맞춘다 |
| 2026-11-20 | K-EXAONE을 GPT의 fallback으로 등록한다. 학습 동의 설정은 확인하지 못한 채 진행한다 | Codex 토큰 격리나 Plus 한도 소진 때 비서가 멈추지 않게 한다. 동의 설정 확인은 미결정 사항에 남긴다 |
| 2026-11-19 | Hermes 설정은 `config.yaml` 대신 `deploy/hermes/configure.sh`로 관리한다 | `config.yaml`은 Hermes가 생성·마이그레이션하는 큰 파일이라 저장소 기준본과 쉽게 어긋난다 |
| 2026-11-20 | 프로젝트 관리는 Slack이 아니라 Notion에 둔다 | DB 간 Relation과 날짜 범위가 필요하고, 혼자 쓰는 용도라 메신저의 이점이 없다 |
| 2026-11-20 | 프로젝트의 단계는 Tasks의 Select가 아니라 Milestones DB로 둔다 | 단계마다 기간과 상태가 있어야 "프로젝트" 캘린더 막대와 대응한다 |
| 2026-11-20 | "프로젝트" 캘린더는 Notion의 사본으로 보고 `sync_project_calendar`가 승인 없이 맞춘다 | Notion Calendar는 Notion 항목을 Google Calendar 이벤트로 만들지 않는다. 사용자가 적었거나 승인한 값을 옮길 뿐이라 승인을 다시 받지 않는다 |
| 2026-11-20 | 프로젝트 점검은 모든 프로젝트를 함께 모의 배치해 계산한다 | 빈 시간을 프로젝트끼리 나눠 쓰므로 따로 계산하면 실제보다 여유 있게 나온다 |
| 2026-11-20 | 프로젝트 분해는 `propose_breakdown` → 승인 → `apply_breakdown`으로 한다 | LLM이 추정한 단계와 소요 시간이 들어가므로 계획 초안과 같은 승인 흐름을 따른다 |
| 2026-11-20 | 마감이 없는 Task는 단계 종료일, 없으면 프로젝트 종료일을 마감으로 쓴다 | 마감이 없으면 배치 순서를 정할 근거가 없다 |
| 2026-11-20 | 주간 시간 배분, Task 선행 관계, 정체 감지, 프로젝트 기록은 보류한다 | 배치 기준을 바꾸거나 관리 부담이 늘어난다. 1\~2주 써 본 뒤 다시 본다 |
