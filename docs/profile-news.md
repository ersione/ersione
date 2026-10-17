# 프로필 소식 자동 갱신

ersione.com의 `/api/profile/news`에서 제목·실제 링크·발행일·정식 릴리스 배지 주소를 받아 README의 `releases`·`posts` 주석 영역만 갱신합니다. 소개, Studio 배너와 프로젝트 링크는 변경하지 않습니다. 서버 API를 HTTPS로 배포한 뒤 적용합니다.

- **만든 것**: 프로젝트 링크 + SVG 릴리스 버전 배지 + 발행일
- **기록한 것**: 글 제목 링크 + 발행일
- 매일 서울 **09:17** 예약과 **Refresh profile news from API → Run workflow** 수동 실행을 지원합니다. GitHub 예약은 지연될 수 있습니다.
- 배지는 같은 API 응답의 버전으로 조회해 `assets/news/release-<SHA256>.svg`에 고정 저장합니다. 제목·이미지·클릭 주소를 함께 갱신하며 과거 배지 파일은 삭제하지 않습니다.
- API·SVG·스키마·주석 검증 중 하나라도 실패하면 기존 README와 배지를 유지하고 커밋 전에 중단합니다. stale/fallback·빈 목록도 성공으로 취급하지 않습니다.
- 모든 응답을 검증한 다음 새 배지를 준비하고 README를 원자적으로 교체합니다. 같은 데이터는 파일을 다시 쓰지 않고 staged diff가 있을 때만 봇이 커밋·푸시합니다.
- API 조회에는 토큰·인증 헤더·쿠키를 보내지 않으며 리다이렉트를 따라가지 않습니다. GitHub의 기본 워크플로 토큰은 커밋·푸시에만 사용합니다.

로컬 검증은 Python 표준 라이브러리만 사용합니다.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/update_readme.py --dry-run
# 별도 README 사본과 로컬 API 서버로 검증
python3 scripts/update_readme.py --readme /path/to/profile-draft.md \
  --api-base http://127.0.0.1:3017 --allow-local --dry-run
```

기본 API origin은 `https://ersione.com`이며 `--allow-local`은 loopback HTTP만 추가로 허용합니다. `--dry-run`을 빼면 README와 배지를 갱신하지만 스크립트는 Git 명령을 실행하지 않습니다. GitHub Camo 캐시로 이미지의 즉시 표시 갱신은 보장하지 않습니다.
