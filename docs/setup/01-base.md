# 기반 단계: 서버 준비와 Hermes 컨테이너 실행

설계 문서 [구현 순서](../homeserver-hermes-architecture.md#구현-순서)의 첫 단계다. 서버에 Ubuntu Server, Tailscale, Docker를 설치하고, 이 저장소를 clone해 Hermes 컨테이너를 빌드·실행한다. 모델 로그인과 Discord 연결은 다음 단계에서 한다.

**완료 기준**

- [ ] 다른 기기에서 Tailscale로만 SSH 접속된다.
- [ ] `hermes` 컨테이너가 `Up` 상태이고, 서버를 재부팅해도 자동으로 다시 뜬다.
- [ ] 컨테이너 안 시각이 KST이고, `uv`가 PATH에 있다.
- [ ] `~/assistant-data`의 파일 소유자가 서버 사용자다.

같은 compose 설정을 데스크톱(x86_64)에서 먼저 띄워 위 항목을 확인했다(2026-11-19, `v0.23.2`). 이미지 크기는 약 4.7GB, 대기 상태 메모리는 약 320MB였다.

## 1. Ubuntu Server

1. Ubuntu Server LTS를 설치한다. 설치 중 "OpenSSH server"를 선택한다.
2. 기본 설정:

   ```sh
   sudo apt update && sudo apt full-upgrade -y
   sudo timedatectl set-timezone Asia/Seoul
   ```

3. 노트북을 서버로 쓴다면 덮개를 닫아도 절전되지 않게 한다. `/etc/systemd/logind.conf`에서 아래 값을 설정하고 `sudo systemctl restart systemd-logind`를 실행한다.

   ```ini
   HandleLidSwitch=ignore
   HandleLidSwitchExternalPower=ignore
   ```

## 2. Tailscale

1. 설치하고 로그인한다. 출력되는 링크를 다른 기기에서 열어 승인한다.

   ```sh
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   tailscale ip -4
   ```

2. Tailscale 관리 콘솔(Machines)에서 이 서버의 **Disable key expiry**를 켠다. 끄지 않으면 기기 키가 만료될 때 서버가 tailnet에서 빠진다.
3. 다른 기기에서 `ssh <사용자>@<서버의 Tailscale 이름 또는 IP>`로 접속되는지 확인한다.
4. 접속이 확인된 뒤에만 방화벽을 켠다. 실수로 막히면 서버 앞에서 직접 로그인해 `sudo ufw disable`로 푼다.

   ```sh
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow in on tailscale0
   sudo ufw enable
   ```

Docker가 공개하는 포트는 ufw 규칙을 우회한다. 그래서 `compose.yaml`에는 `ports:`를 두지 않는다.

## 3. Docker

Docker 공식 apt 저장소로 설치한다. 명령이 바뀌었을 수 있으므로 [공식 문서](https://docs.docker.com/engine/install/ubuntu/)와 다르면 공식 문서를 따른다.

```sh
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"   # 다시 로그인해야 적용된다
```

다시 로그인한 뒤 `docker run --rm hello-world`로 확인한다.

## 4. 저장소 clone

이 저장소는 GitHub private 저장소에 두고, 서버는 읽기 전용 deploy key로 받는다.

```sh
ssh-keygen -t ed25519 -f ~/.ssh/assistant_deploy -N "" -C "homeserver deploy"
cat ~/.ssh/assistant_deploy.pub
```

출력된 공개 키를 GitHub 저장소 Settings → Deploy keys에 추가한다("Allow write access"는 끈다). 그 다음 `~/.ssh/config`에 아래를 추가하고 clone한다.

```
Host github-assistant
  HostName github.com
  User git
  IdentityFile ~/.ssh/assistant_deploy
  IdentitiesOnly yes
```

```sh
git clone git@github-assistant:<GitHub 사용자>/assistant.git ~/assistant
```

## 5. 상태 디렉터리와 `.env`

```sh
mkdir -p ~/assistant-data && chmod 700 ~/assistant-data
cd ~/assistant
cp deploy/.env.example deploy/.env
sed -i "s|^DATA_DIR=.*|DATA_DIR=$HOME/assistant-data|; s|^HOST_UID=.*|HOST_UID=$(id -u)|; s|^HOST_GID=.*|HOST_GID=$(id -g)|" deploy/.env
cat deploy/.env
```

`deploy/.env`는 compose 변수만 담는다. API 키 같은 Hermes 비밀 값은 이후 단계에서 `~/assistant-data/.env`에 들어간다.

## 6. 빌드와 실행

compose 명령이 길어서 별칭을 둔다(`~/.bashrc`에 추가).

```sh
alias dc='docker compose -f ~/assistant/deploy/compose.yaml'
```

```sh
dc up -d --build
```

첫 빌드는 공식 이미지(약 4.7GB)를 받느라 오래 걸린다. 이후에는 바뀐 레이어만 다시 빌드한다.

## 7. 확인

```sh
dc ps                                         # hermes ... Up
dc logs --tail 50                             # "Hermes Gateway Starting..."
dc exec hermes date                           # ... KST
dc exec --user hermes hermes uv --version     # uv 0.13.5
ls -ln ~/assistant-data                       # 소유자 UID가 `id -u`와 같음
dc exec hermes hermes status --full
docker stats --no-stream hermes
```

마지막으로 `sudo reboot` 후 다시 접속해 `dc ps`가 `Up`인지 확인한다.

**지금 단계에서 정상인 경고**

- `Nous Portal ... not logged in`, `OpenAI Codex ✗ not logged in`: 모델 단계에서 로그인한다.
- `install out of sync (pnpm: not installed or outdated)`: 공식 이미지가 내는 경고다. 로컬 테스트에서 게이트웨이 기동에는 영향이 없었다.

## 자주 쓰는 명령

| 목적 | 명령 |
| --- | --- |
| 배포 (코드·설정 변경 반영) | `cd ~/assistant && git pull && dc up -d --build` |
| 로그 보기 | `dc logs -f` 또는 `tail -F ~/assistant-data/logs/gateways/default/current` |
| 재시작 | `dc restart` |
| 컨테이너 안 Hermes 명령 | `dc exec hermes hermes <명령>` |
| Hermes 버전 올리기 | `deploy/Dockerfile`의 `HERMES_VERSION`을 바꿔 커밋하고 배포 |
