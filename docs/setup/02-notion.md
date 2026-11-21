# Notion 단계: DB 생성과 integration 연결

설계 문서 [Notion 스키마](../homeserver-hermes-architecture.md#notion-스키마)대로 DB 네 개를 만들고, planner MCP가 쓸 integration 토큰을 발급해 이 DB들에만 공유한다.

**완료 기준**

- [x] "비서" 페이지 아래에 Projects, Milestones, Tasks, Jobs DB가 문서 스키마대로 있다.
- [x] integration 토큰을 발급해 서버 `~/assistant-data/.env`에 넣었다. (2026-11-20, 사용자)
- [x] integration이 "비서" 페이지에만 연결되어 있다. (2026-11-20, 사용자)
- [ ] 토큰 동작 확인: planner MCP v1에서 `list_tasks`

## 1. DB (2026-11-20 생성 완료)

Claude가 Notion 커넥터로 만들었다. 워크스페이스는 개인 Gmail 계정의 **Hermes Assistant**이고, 부모 페이지는 그 안의 개인 페이지 "비서"다. (처음에 학교 계정 워크스페이스에 잘못 만든 DB는 휴지통으로 보냈다.)

| DB | 데이터 소스 ID | 제목 속성 |
| --- | --- | --- |
| [비서](https://app.notion.com/p/41da70a526e78172bef2d121718492b8) (부모 페이지) | — | — |
| [Projects](https://app.notion.com/p/41da70a526e78108a487f13df025e2d2) | `41da70a5-26e7-813d-8604-000b2e8a24f3` | 이름 |
| [Milestones](https://app.notion.com/p/41da70a526e7812ca1d1d8f918074395) | `41da70a5-26e7-8187-a6e6-000bb3282705` | 이름 |
| [Tasks](https://app.notion.com/p/41da70a526e781e597f8ea922993fe4c) | `41da70a5-26e7-810a-a6fc-000b620b0253` | 제목 |
| [Jobs](https://app.notion.com/p/41da70a526e78168a6d4d6fd046999c8) | `41da70a5-26e7-81d7-bc8b-000b625312f0` | 회사 |

ID는 비밀 값이 아니다. planner MCP는 이 데이터 소스 ID를 `planner.yaml`에서 읽는다.

**문서 스키마에 더해 생긴 것**

- 양방향 관계라서 반대쪽 속성이 자동으로 생겼다: Projects의 `단계`(→ Milestones), Projects의 `할 일`(→ Tasks), Milestones의 `할 일`(→ Tasks). Notion이 관리하므로 코드는 Tasks·Milestones 쪽만 쓴다.
- Status 그룹(코드는 그룹으로 판단한다):

  | DB | 할 일(to_do) | 진행(in_progress) | 완료(complete) |
  | --- | --- | --- | --- |
  | Projects | 보류 | 진행 | 완료 |
  | Milestones | 예정 | 진행 | 완료 |
  | Tasks | 할 일 | 진행 | 완료 |
  | Jobs | 관심 | 지원, 서류, 면접 | 결과 |

- 새 항목의 기본 상태는 각 DB의 첫 to_do 옵션이다. Projects는 `보류`로 시작하므로 만들 때 `진행`으로 바꾼다.

## 2. integration 토큰 발급 (직접)

1. https://www.notion.so/profile/integrations 에서 **새 integration**을 만든다.
   - 종류: **Internal**, 워크스페이스: **Hermes Assistant**
   - 이름: 예) `assistant-planner`
2. **Capabilities**는 필요한 것만 켠다.
   - 콘텐츠: Read, Update, Insert 켬
   - 댓글: 끔
   - 사용자 정보: **No user information**
3. **Internal Integration Secret**을 복사해 서버 `.env`에 편집기로 넣는다. 명령줄이나 대화에 붙여 넣지 않는다.

   ```sh
   ssh server
   nano ~/assistant-data/.env
   ```

   ```
   NOTION_TOKEN=복사한값
   ```

## 3. DB 공유 (직접)

1. Notion에서 "비서" 페이지를 연다.
2. 오른쪽 위 `•••` → **연결(Connections)** → 방금 만든 integration을 추가한다.
3. 하위 DB 네 개에 자동으로 적용된다. 다른 페이지에는 연결하지 않는다.

"비서" 페이지 아래에 다른 페이지를 만들면 그 페이지도 integration이 읽을 수 있다. 이 페이지는 DB 네 개만 두는 용도로 쓴다.

토큰이 동작하는지는 planner MCP v1 단계에서 `list_tasks`로 확인한다.
