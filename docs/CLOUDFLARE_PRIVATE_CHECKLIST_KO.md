# Cloudflare Pages 비공개 배포 체크리스트

## 1. Pages 프로젝트 만들기

- [ ] Cloudflare Pages 열기: https://pages.cloudflare.com/
- [ ] Create a project
- [ ] Connect to Git
- [ ] GitHub repo 선택: `presentjinho/optimizerzero`
- [ ] Project name: `optimizerzero`
- [ ] Production branch: `main`
- [ ] Build command: 비움
- [ ] Build output directory: `web`
- [ ] `wrangler.toml` 확인: `pages_build_output_dir = "./web"`
- [ ] Deploy

주의: `wrangler.toml`을 Cloudflare Pages 설정으로 쓰면 이 파일이 Pages 설정의 기준이 된다. Cloudflare dashboard에서 이미 다른 설정을 먼저 만들었다면 배포 전 dashboard 설정과 `wrangler.toml`이 같은지 확인한다.

## 2. 배포 직후 확인

- [ ] `https://optimizerzero.pages.dev` 또는 Cloudflare가 준 URL 접속
- [ ] 첫 화면에 `OptimizerZero Web Lite` 표시
- [ ] 목적 프리셋이 보임
- [ ] `robots.txt` 접속 시 `Disallow: /` 표시
- [ ] `manifest.webmanifest` 접속 가능
- [ ] `service-worker.js` 접속 가능

## 3. Access로 진짜 비공개 잠금

Cloudflare Pages URL은 기본 public이다. 아래를 끝내야 진짜 비공개다.

- [ ] Cloudflare Zero Trust 열기
- [ ] Access > Applications
- [ ] Add application
- [ ] Self-hosted 선택
- [ ] Application name: `OptimizerZero`
- [ ] Application domain: `optimizerzero.pages.dev`
- [ ] Policy name: `Owner only`
- [ ] Action: `Allow`
- [ ] Include rule: `Emails`
- [ ] Value: 내 이메일 주소
- [ ] Save

## 4. 잠금 검증

- [ ] 시크릿 창에서 배포 URL 열기
- [ ] Cloudflare Access 로그인/이메일 인증 화면이 먼저 뜸
- [ ] 허용한 이메일로 인증 후 앱 진입 가능
- [ ] 허용하지 않은 이메일은 접근 불가

## 5. 공개 전환할 때 제거할 것

공개 출시 전에는 아래를 바꾼다.

- [ ] Cloudflare Access 제한 해제 또는 public 경로 분리
- [ ] `web/robots.txt`의 `Disallow: /` 제거
- [ ] `web/_headers`의 `X-Robots-Tag` 제거
- [ ] `web/index.html`의 `robots` meta 제거
- [ ] README에 공개 URL 추가

## 6. 배포 URL 기록

```text
Cloudflare Pages URL:
Access policy:
Allowed email:
Public launch date:
```
