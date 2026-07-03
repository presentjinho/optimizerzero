# 무료로 계속 열어두는 배포 전략

## 결론

가장 좋은 무료 조합:

1. Cloudflare Pages: `optimizerzero.pages.dev`
2. Netlify: `optimizerzero.netlify.app`
3. GitHub Pages 백업: `username.github.io/optimizerzero`

OptimizerZero Web Lite는 정적 파일만 쓰므로 서버 비용 없이 오래 열어두기 좋다.

## 추천 1: Cloudflare Pages

장점:

- 무료 플랜에서 정적 요청/대역폭이 넉넉함
- `*.pages.dev` 무료 주소 제공
- 커스텀 도메인 연결 가능
- PWA 캐시와 잘 맞음

사용법:

1. GitHub에 이 프로젝트 업로드
2. Cloudflare Pages에서 repo 연결
3. Build command 비움
4. Publish directory: `web`
5. 배포 후 주소 예: `optimizerzero.pages.dev`

## 추천 2: Netlify

장점:

- `web/` 폴더를 드래그 앤 드롭해서 바로 배포 가능
- `*.netlify.app` 무료 주소 제공
- `netlify.toml` 이미 포함

사용법:

1. Netlify Drop 열기
2. `web/` 폴더 업로드
3. 사이트 이름을 `optimizerzero` 같은 이름으로 변경
4. 주소 예: `optimizerzero.netlify.app`

## 추천 3: GitHub Pages

장점:

- GitHub repo만 있으면 무료
- 프로젝트 신뢰도/소스 공개에 좋음
- 백업 배포지로 적합

주의:

- URL이 `username.github.io/repo` 형태라 덜 예쁨
- PWA scope가 하위 경로일 때 꼼꼼히 확인 필요

## 도메인 선택

완전 무료:

- `optimizerzero.pages.dev`
- `optimizerzero.netlify.app`
- `username.github.io/optimizerzero`

더 신뢰감 있는 유료 도메인:

- `optimizerzero.com`
- `optimizerzero.app`
- `ozero.app`
- `filezero.app`

무료 호스팅 + 유료 도메인이 현실적으로 가장 안정적이다.

## 계속 열어두기 체크리스트

- 정적 파일만 사용한다.
- 서버 저장/로그인/DB를 붙이지 않는다.
- 파일 처리는 브라우저에서만 한다.
- PWA 캐시를 켜서 재방문 가능하게 한다.
- GitHub repo를 원본 저장소로 둔다.
- Cloudflare Pages를 메인, Netlify를 백업으로 둔다.
- 큰 파일/PDF는 데스크톱 버전으로 안내한다.

## 공유 문구

설치 없이 쓰는 목적별 압축기.

보관용, 공유용, 메신저용, 이메일용, 품질 우선 중에서 고르면 손실 허용도와 품질을 자동 추천합니다.
파일은 서버로 올라가지 않고 브라우저 안에서 처리됩니다.
