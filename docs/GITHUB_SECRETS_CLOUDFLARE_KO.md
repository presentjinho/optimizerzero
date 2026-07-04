# GitHub Actions Cloudflare secrets 설정

이 문서는 `Deploy Cloudflare Pages` workflow를 GitHub에서 수동 실행하기 전에 필요한 secret 설정만 다룬다.

## 필요한 secret

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

값은 문서나 코드에 붙여넣지 않는다. GitHub repository secret에만 저장한다.

## GitHub에 넣는 위치

1. GitHub repo `presentjinho/optimizerzero` 열기
2. Settings
3. Secrets and variables
4. Actions
5. New repository secret
6. `CLOUDFLARE_API_TOKEN` 저장
7. New repository secret
8. `CLOUDFLARE_ACCOUNT_ID` 저장

## Cloudflare API token 권한

최소 권한 원칙:

- Account: Cloudflare Pages edit 권한
- 대상 account: 본인 Cloudflare account

권한 이름은 Cloudflare UI 변경에 따라 조금 다를 수 있다. Pages 프로젝트를 직접 업로드/수정할 수 있는 token이어야 한다.

## 배포 실행

1. GitHub repo > Actions
2. `Deploy Cloudflare Pages`
3. Run workflow
4. branch: `main`
5. Run workflow 클릭

workflow는 먼저 `verify-web.ps1`를 실행하고, 통과한 뒤 `web` 폴더를 Cloudflare Pages에 배포한다.

## 실패 시 확인

- secret 이름이 정확한지 확인한다.
- token 값 앞뒤에 공백이 들어가지 않았는지 확인한다.
- `CLOUDFLARE_ACCOUNT_ID`가 token을 만든 account와 같은지 확인한다.
- Cloudflare Pages project name이 `optimizerzero`인지 확인한다.
- workflow 로그에서 `Verify Web Lite` 단계가 먼저 실패했는지, `Deploy` 단계가 실패했는지 분리해서 본다.

## 보안 주의

- token은 README, issue, commit, 채팅에 붙여넣지 않는다.
- token을 실수로 노출했다면 Cloudflare에서 즉시 revoke하고 새 token을 만든다.
- Cloudflare Access 설정 전까지 Pages URL은 public일 수 있다.
