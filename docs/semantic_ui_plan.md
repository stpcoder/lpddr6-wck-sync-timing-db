# Semantic UI Plan

이 UI는 JEDEC PDF viewer가 아니라 symbol 기반 timing DB 조회 도구다.

## 화면 구성

1. 계산 결과표
   - WCK Sync-Off timing 판단을 위한 주 화면이다.
   - Current CMD, Next CMD, bank relation, burst, 검증할 CMD 간격, WS operand, MR1.OP[4:0], WLS, DEFF, DVFSL, Write Link, Read Link를 입력한다.
   - 여러 값을 쉼표로 넣으면 모든 조합을 sweep해서 `RL`, `WL`, `tWTR`, `tRTW`, `WR->RD min` 같은 결과를 표로 만든다.
   - 기본값은 `MR1.OP[4:0]`에서 data rate와 tCK를 자동으로 잡는다. Data Rate 직접 입력은 검증용 예외 모드다.

2. 단일 Scenario
   - 하나의 command pair와 조건을 넣고 allowed/too-early/not-allowed 및 trace를 확인한다.

3. Symbol 구성
   - symbol 검색, kind filter, source/description/formula/table key 확인.
   - 예: `RL`을 고르면 `MR1.OP[4:0]`, latency table selector, read/write link protection, DVFSL/DEFF 조건이 어떻게 RL을 구성하는지 확인.
   - 계산표를 만들기 위해 꼭 먼저 고를 필요는 없다. 계산값의 근거를 추적할 때 쓰는 보조 화면이다.

4. Graph
   - target symbol의 upstream dependency와 downstream usage를 동시에 Graphviz로 표시.
   - 개발자용 검증 화면이다.

5. DB 구축 현황
   - graph-backed 범위와 아직 남은 unresolved/not-started 범위를 확인.

## 실행

의존성 없이 바로 실행:

```bash
python3 tools/semantic_ui_server.py --port 8765
```

Streamlit UI 의존성 설치:

```bash
python3 -m pip install -r ui/requirements.txt
```

Streamlit UI 실행:

```bash
python3 -m streamlit run ui/streamlit_app.py --server.port 8501
```

패키지 설치 없이 CLI로 같은 semantic query를 확인할 수 있다.

```bash
python3 tools/query_lpddr6_semantic_db.py detail WR_TO_RD_DIFF

python3 tools/query_lpddr6_semantic_db.py sweep \
  --current-cmd WR \
  --next-cmd RD \
  --match-mr1-speed-bin \
  --mr1 01011,01100,01101 \
  --efficiency 0,1 \
  --dvfsl 0,1 \
  --write-link 0,1 \
  --outputs "RL,WL,tCK_ns,tWTR_S,tWTR_L,WR->RD min (diff BG),tRTW"
```

## 다음 확장

1. generic target-symbol resolver
   - 지금 evaluator는 fixed phase order를 유지한다.
   - 다음 단계는 `target_symbol`을 입력받으면 dependency graph를 따라 필요한 lookup/formula만 resolve하는 방식이다.

2. condition AST registry
   - selector 조건을 evaluator 함수가 아니라 CSV/JSON condition AST로 분리한다.

3. cached analytical table
   - 자주 쓰는 sweep 결과를 `data/cache/*.csv` 또는 DuckDB로 저장해 UI 조회 속도를 높인다.

4. LPDDR5 comparison layer
   - 동일 symbol id에 `spec=LPDDR5/LPDDR6` dimension을 추가해 차이만 filter한다.
