# KMA Weather (기상청 동네예보) — Home Assistant 통합

기상청 **동네예보 공식 API**(공공데이터포털 `data.go.kr`)를 쓰는 Home Assistant 커스텀 통합.
기상청이 주는 정보(현재 + 시간별 + 일별)를 **`weather.<name>` 엔티티 하나**에 담는다 — 정부 1차
출처, 결정론적 8회/일 갱신, 무료.

## 설치 (HACS)

1. HACS → ⋮ → **사용자 지정 저장소(Custom repositories)** → `https://github.com/gamma4d/ha-kma-weather`
   추가, 카테고리 **Integration**.
2. 목록에서 **KMA Weather** → **다운로드** → **Home Assistant 재시작**.
3. 설정 → 기기 및 서비스 → **[통합구성요소 추가]** → **"KMA"** 검색 → **KMA Weather**:
   - **인증키(Decoding)**: data.go.kr 단기예보 조회서비스(데이터셋 `15084084`) 활용신청 후
     마이페이지의 **일반 인증키(Decoding)**. ⚠ Encoding 키 아님. 발급 후 1~2시간 뒤 활성화.
   - **이름**: 엔티티 슬러그(예 `home`). **위경도**: 비우면 HA 홈 좌표 사용.
   - 제출 시 **라이브로 키 검증** → 통과하면 엔티티 자동 생성.

## 제공: `weather.<name>` 엔티티 하나

- **현재값**: 상태(condition) + 속성 `temperature` / `humidity` / `wind_speed`(m/s) / `wind_bearing`.
- **예보**: `weather.get_forecasts` 서비스로 조회 — `hourly`(24시간) / `daily`(단기예보가 주는 ~5일).
  각 항목: `datetime, condition, native_temperature, native_templow(일별),
  humidity, precipitation_probability(강수확률), native_precipitation(강수량),
  native_wind_speed, wind_bearing`.

흩어진 항목별/시각별 센서는 만들지 않음(HA 표준: forecast는 엔티티 안의 리스트).

## 데이터 매핑

기온 T1H/TMP · 습도 REH · 강수확률 POP · 강수량 RN1/PCP · 일 최고/최저 TMX/TMN ·
날씨상태 SKY+PTY · 풍속/풍향 WSD/VEC. 위치는 위경도→5km 격자(nx,ny) 자동 변환.
(미세먼지/공기질은 기상청 범위 밖 — 에어코리아 별도, 미포함.)

## 라이선스 / 데이터

코드 MIT. 날씨 데이터 © 기상청(KMA), 공공데이터포털 `data.go.kr` 이용약관에 따름.
