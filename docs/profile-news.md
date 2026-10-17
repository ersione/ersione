# 프로필 소식 자동 갱신

프로필 README의 `releases`와 `posts` 주석 사이만 GitHub Actions로 갱신합니다.
소개, 배너, 프로젝트 링크는 자동 갱신 대상이 아닙니다.

- 블로그 RSS에서 발행일 기준 최근 글 2개를 표시합니다. 미래 발행일의 글은 제외합니다.
- Ersione Design System, Ersione’s Studio, Company Lens의 공개 릴리스 중 최근 정식 릴리스를 최대 2개 표시합니다. 초안과 사전 릴리스는 제외합니다.
- 매일 한국 시간 09:17·21:17에 실행하도록 예약하며, GitHub Actions 상황에 따라 실행이 늦어질 수 있습니다.
- Actions의 **Refresh profile news → Run workflow**로 수동 갱신할 수 있습니다.
- 내용이 달라질 때만 봇이 README를 커밋합니다. 별도 개인 토큰 없이 실행 시 발급되는 `GITHUB_TOKEN`을 사용합니다.
- 소스 조회나 검증이 실패하면 해당 영역의 기존 내용을 유지하고 실행 결과를 실패로 표시합니다. 다른 소스가 정상이라면 그 영역은 갱신합니다.
- 자동 갱신 커밋은 추가 워크플로 실행을 유발하지 않습니다. 워크플로는 이 저장소의 기본 브랜치에서만 내용을 게시합니다.

로컬 검증:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/update_readme.py
```

로컬 실행은 README를 갱신하며 커밋하거나 푸시하지 않습니다.
