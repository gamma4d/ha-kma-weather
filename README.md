# KMA Weather (기상청 동네예보) — Home Assistant 통합

기상청 **동네예보 공식 API**(공공데이터포털 `data.go.kr`)를 직접 쓰는 Home Assistant 커스텀 통합.
정부 1차 출처 · 결정론적 8회/일 갱신 · 무료. 온도·습도·강수확률·시간당강수량·최고/최저기온·
날씨상태 + **예보(1시간 / 3시간 / 1일)** 제공.

## 설치 (HACS)

1. HACS → ⋮ → **사용자 지정 저장소(Custom repositories)** → `https://github.com/gamma4d/ha-kma-weather`
   추가, 카테고리 **Integration**.
2. 목록에서 **KMA Weather** → **다운로드** → **Home Assistant 재시작**.
3. 설정 → 기기 및 서비스 → **[통합구성요소 추가]** → **"KMA"** 검색 → **KMA Weather**:
   - **인증키(Decoding)**: data.go.kr 단기예보 조회서비스(데이터셋 `15084084`) 활용신청 후
     마이페이지의 **일반 인증키(Decoding)**. ⚠ Encoding 키 아님. 발급 후 1~2시간 뒤 활성화.
   - **이름**: 엔티티 슬러그(예 `bundang`). **위경도**: 비우면 HA 홈 좌표 사용.
   - 제출 시 **라이브로 키 검증** → 통과하면 엔티티 자동 생성.

## 제공 엔티티 (`name: bundang` 기준)

- `weather.bundang` — 현재 상태/기온/습도 + **hourly·daily 예보**(`weather.get_forecasts`)
- `sensor.bundang_temperature` / `_humidity` / `_precipitation`(시간당) /
  `_precipitation_probability`(PoP) / `_temperature_max` / `_temperature_min` / `_condition`
- `sensor.bundang_forecast_1h` / `_forecast_3h` / `_forecast_daily` — 각 예보 list를 `forecast` 속성으로
  (HA에 3시간 네이티브 forecast 타입이 없어 센서로 제공)

## 데이터 매핑

온도 T1H/TMP · 습도 REH · 강수확률 POP · 시간당강수량 RN1/PCP · 최고/최저 TMX/TMN ·
날씨상태 SKY+PTY. 위치는 위경도→5km 격자(nx,ny) 자동 변환. 미세먼지(PM)는 범위 밖(에어코리아 별도).

## 라이선스 / 데이터

코드 MIT. 날씨 데이터 © 기상청(KMA), 공공데이터포털 `data.go.kr` 이용약관에 따름.
