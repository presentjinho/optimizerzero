# 비공개 무료 배포 절차

## 결론

가장 좋은 방식:

1. GitHub private repository
2. Cloudflare Pages 연결
3. Cloudflare Access로 사이트 잠금

이렇게 하면 내 PC를 끄고도 계속 열리고, 링크를 알아도 허용된 이메일만 접근할 수 있다.

## 중요한 사실

Cloudflare Pages URL은 기본적으로 public이다.

비공개로 쓰려면 둘 중 하나가 필요하다.

- 진짜 비공개: Cloudflare Access 적용
- 임시 비공개: private GitHub repo + 링크 미공유 + noindex

OptimizerZero는 `robots.txt`, `<meta name="robots">`, `_headers`에 noindex를 넣어 검색 노출을 막는다.
하지만 noindex는 접근 제한이 아니라 검색 회피다.

## 추천 설정

GitHub:

- repo name: `OptimizerZero`
- visibility: Private
- default branch: `main`

Cloudflare Pages:

- project name: `optimizerzero`
- build command: 비움
- publish directory: `web`
- production branch: `main`
- repo config: `wrangler.toml` includes `pages_build_output_dir = "./web"`

`wrangler.toml`을 쓰면 Cloudflare Pages에서 이 파일이 설정 기준이 된다. 이미 dashboard에서 프로젝트를 만든 뒤 설정을 바꿨다면, 배포 전에 dashboard 설정과 파일 설정이 같은지 확인한다.

Cloudflare Access:

- application type: Self-hosted
- domain: `optimizerzero.pages.dev`
- policy: Allow
- rule: Emails
- allowed emails: 본인 이메일만 먼저 추가

## 순서

1. GitHub에서 private repo 생성
2. 이 폴더를 repo에 push
3. Cloudflare Pages에서 GitHub repo 연결
4. 배포 확인
5. Cloudflare Zero Trust > Access > Applications에서 Pages 주소 잠금
6. 내 이메일로 접속 테스트
7. 필요할 때만 테스트 사용자 이메일 추가

세부 체크리스트는 `docs/CLOUDFLARE_PRIVATE_CHECKLIST_KO.md`를 따른다.

## CLI 직접 배포

Cloudflare dashboard 연결 전에 수동 업로드로 먼저 확인하려면:

```powershell
.\deploy-cloudflare.ps1
.\deploy-cloudflare.ps1 -Deploy
```

첫 명령은 검증과 배포 명령 출력만 한다. 실제 업로드는 `-Deploy`를 붙였을 때만 실행된다.
Cloudflare 로그인은 Wrangler 브라우저 로그인 또는 `CLOUDFLARE_API_TOKEN` 환경변수가 필요할 수 있다.

## GitHub Actions 수동 배포

PC를 켜지 않고 GitHub에서 배포 버튼으로 올리려면 repository secret을 먼저 추가한다.

- `CLOUDFLARE_API_TOKEN`: Cloudflare Pages Edit 권한이 있는 API token
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare account ID

그 다음 GitHub Actions에서 `Deploy Cloudflare Pages` workflow를 수동 실행한다.
이 workflow는 자동 배포가 아니라 `workflow_dispatch` 버튼 실행만 허용한다.

## 공개 전환할 때

공개로 전환하려면:

1. Cloudflare Access policy 제거 또는 public path로 변경
2. `web/robots.txt` 삭제 또는 허용으로 변경
3. `web/_headers`의 `X-Robots-Tag` 제거
4. `index.html`의 robots meta 제거
5. README와 공유글에 공개 URL 추가

## 왜 Netlify보다 이 방식인가

Netlify의 깔끔한 password protection은 유료 플랜 성격이 강하다.
무료로 private access까지 가져가려면 Cloudflare Pages + Cloudflare Access 조합이 더 낫다.
