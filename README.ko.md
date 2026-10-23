# Download Only Torrent

**BitTorrent 파일 조각 데이터 업로드를 차단하도록 설계한 Windows용 오픈소스 다운로드 클라이언트**입니다.

[English](README.md) · [한국어](README.ko.md)

[![Tests](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/tests.yml/badge.svg)](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/tests.yml)
[![Windows build](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/windows-build.yml/badge.svg)](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/windows-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Windows 10/11 (64비트)** · Python + PySide6 · 수정된 libtorrent 2.1.1 · 한국어 / English

> **‘다운로드 전용’의 의미:** 공식 Windows 빌드에서는 libtorrent의 BitTorrent **PIECE 데이터 전송 경로를 제거**하고 추가 안전장치를 적용합니다. 하지만 트래커·DHT 요청, 핸드셰이크, 데이터 조각 요청, TCP ACK 등 **프로토콜 및 제어 트래픽은 여전히 송신**합니다. 모든 업로드 대역폭을 0으로 만드는 프로그램이나 익명화 도구는 아닙니다.

## 다운로드 및 실행

1. [최신 릴리스](https://github.com/Kwon-dev/download-only-torrent/releases/latest)를 엽니다.
2. **DownloadOnlyTorrent-windows-x64-…zip** 파일을 다운로드합니다. 최신 릴리스에 아직 ZIP이 없다면 Windows 릴리스 빌드가 진행 중일 수 있으므로 [Actions](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/windows-build.yml)를 확인하세요.
3. ZIP 파일의 **전체 내용을** 원하는 폴더에 압축 해제합니다.
4. 압축을 푼 폴더에서 `DownloadOnlyTorrent.exe`를 실행합니다. 옆의 파일과 폴더는 삭제하거나 분리하지 마세요. 이 프로그램은 **onedir 방식**으로 배포됩니다.

공식 Windows 실행 파일만 사용할 경우 Python, Visual Studio, vcpkg를 설치할 필요가 없습니다. 이들은 소스에서 직접 빌드할 때만 필요합니다.

## 주요 기능

| 기능 | 설명 |
| --- | --- |
| **다운로드 전용 정책** | 수정된 libtorrent 및 검증 절차로 BitTorrent 파일 조각 데이터 업로드를 차단 |
| **파일별 선택** | 토렌트나 마그넷의 내부 파일 목록을 확인하고 원하는 파일만 다운로드 |
| **작은 파일 자동 제외** | 설정한 크기 이하 파일의 체크를 자동 해제하여 부가 파일을 쉽게 제외 |
| **다운로드 재개** | 활성 작업과 재개 데이터를 저장해 재시작 시 복원하고 불필요한 재검사를 줄임 |
| **편리한 데스크톱 UI** | 여러 토렌트 추가, 정렬, 일괄 조작, 피어 진단, 트레이 및 완료 알림 |
| **네트워크 설정** | 속도·피어·수신 인터페이스·IPv6·피어 탐색·추가 트래커 등 조정 |

`.torrent` 파일, 마그넷 링크, Windows 파일·프로토콜 연결, 다크·라이트 테마, 한국어·영어 UI를 지원합니다.

## 사용 방법

1. **.torrent 추가**에서 하나 이상의 토렌트를 선택하거나, **마그넷 추가**에 마그넷 주소를 붙여넣습니다. Windows에서 연결된 파일·링크를 직접 열 수도 있습니다.
2. 파일 선택 창에서 파일 체크 상태를 확인하고 저장 경로를 선택합니다.
3. 다운로드를 시작합니다. 메인 화면에서 진행률·피어·속도를 확인할 수 있습니다.
4. **선택한 파일**의 다운로드가 모두 끝나면 작업이 세션과 목록에서 제거되며, 다운로드한 파일은 유지됩니다.

### 특정 용량 이하 파일 자동 제외

**설정 → 일반 → 파일 크기 필터**에서 **설정한 크기 이하 파일 자동 제외**를 켜고 원하는 수치(예: **10MB**)를 입력합니다.

- **기본값은 꺼짐(OFF)**이며, 변경한 설정은 저장됩니다.
- 설정값 **이하**의 파일은 처음에 체크 해제되고, 큰 파일은 선택됩니다.
- 크기 기준에서 **1MB = 1,000,000바이트**입니다.
- 새 토렌트·마그넷의 파일 선택에 적용되며, 이미 추가한 다운로드에 소급 적용되지는 않습니다.
- 자동으로 제외된 파일도 파일 선택 창에서 다시 체크할 수 있습니다.

**참고:** BitTorrent는 파일 단위가 아니라 데이터 조각(piece) 단위로 수신합니다. 파일 경계에 걸친 조각 때문에 체크 해제한 이웃 파일의 일부 데이터도 함께 받아야 할 수 있습니다.

## 단축키

| 단축키 | 동작 |
| --- | --- |
| `Ctrl+O` | `.torrent` 파일 하나 이상 추가 |
| `Ctrl+M` | 마그넷 링크 추가 |
| `Space` | 선택 작업 일시정지/재개 |
| `Delete` | 선택 작업 제거(확인 창 표시) |
| `Ctrl+A` | 모든 행 선택 |
| `Alt+Enter` | 토렌트 속성/진단 |
| `Ctrl+D` | 세션 진단 |
| `Ctrl+,` | 설정 |
| `Ctrl++` / `Ctrl+-` | 행 높이 조정 |

## 사용 전 주의사항

- **시딩 및 파일 조각 업로드 불가:** 다운로드 완료 후 일반적인 시딩이나 업로드 비율 확보가 불가능하도록 설계됐습니다.
- **비공개 트래커:** 클라이언트 허용 목록, 시딩 시간, 업로드 비율 규칙이 있을 수 있습니다. **이 프로그램의 동작을 허용하지 않는 곳에서는 사용하지 마세요.** 규정 우회용으로 제작한 프로그램이 아닙니다.
- **네트워크 송신 자체를 차단하지는 않음:** 제어 트래픽 등은 여전히 발생합니다.
- **저작권:** 사용 권한이 있는 콘텐츠만 다운로드해야 합니다.

구체적인 차단 방식과 빌드 검증은 [기술 문서](docs/TECHNICAL.md)를 참고하세요.

## 개발 및 기여

- [개발 가이드 — 빌드·테스트·CI](docs/DEVELOPMENT.md)
- [기술 문서 — 구조·다운로드 전용 정책](docs/TECHNICAL.md)
- [이슈 및 버그 제보](https://github.com/Kwon-dev/download-only-torrent/issues)
- [소스 코드](https://github.com/Kwon-dev/download-only-torrent)

버그 제보 시 릴리스 태그 또는 빌드 번호, Windows 버전, 재현 방법을 함께 알려주세요. 보안 관련 문제를 공개 이슈로 올릴 때는 비밀번호 등 민감한 정보를 포함하지 마세요.

## 라이선스

프로젝트 자체 소스 코드는 [MIT 라이선스](LICENSE)로 제공됩니다. 포함된 타사 구성 요소에는 별도 라이선스가 적용됩니다. [타사 고지](THIRD_PARTY_NOTICES.md), [Qt/PySide6 소스 제공 안내](QT_LGPL_SOURCE_OFFER.md), [LICENSES](LICENSES)를 확인하세요.

공식 패키지에는 의존성 라이선스·소스 변환 스크립트와 빌드 출처 및 해시를 기록한 `PATCHED_LIBTORRENT_BUILD.txt`가 포함됩니다.

