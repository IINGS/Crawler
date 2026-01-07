# 목차

1. **Intro**
2. **프로젝트 구조**
3. **Prerequisite**
4. **실행 및 결과 확인**
5. **새로운 사이트 추가하기**
6. **CSS selector 팁**
7. **트러블슈팅**

# 📌Intro

<img width="1853" height="371" alt="image" src="https://github.com/user-attachments/assets/60be7e1b-dce7-4a1c-9cce-d1e087fd383f" />


이 프로그램은 기업 정보(기업명, 대표자, 인증현황 등)를 다양한 웹사이트에서 수집하여 **Google Spreadsheet로 자동 전송**하는 자동화 도구다. 사람이 일일이 검색하고 복사/붙여넣기 하는 시간을 줄이기 위해 제작됐다.

- **Python 크롤러:** 설정된 사이트를 돌아다니며 데이터를 긁어옴
- **Webhook:** 긁어온 데이터를 JSON 형태로 포장해서 구글 서버로 쏘아 보냄
- **Google Sheet:** 받은 데이터를 시트에 차곡차곡 쌓음 (중복 데이터는 크롤러 DB에서 필터링됨)

# 📌프로젝트 구조

```jsx
📂 crawling engine
├┬─ 📂 configs        # (중요) 수집 사이트별 설정 파일 (.json)
│├─ 사이트A.json
│└─ 사이트B.json
│
├┬─ 📂 core           # 웬만하면 건드릴 일 없음 (엔진 핵심 로직)
│├─ engine.py
│├─ hooks.py
│├─ network.py
│└─ strategies.py
│
├── 📂 hooks          # (중요) 복잡한 사이트 전용 파이썬 코드 (.py)
│
├── 📂 states         # 중복 수집 방지용 데이터베이스 (.db) - 수집 안되면 삭제해볼 것
│
├┬─ 📂 utils          # 기타 도구들
│├─ data_processor.py
│├─ smart_extractor.py
│└─ state_manager.py
│
├── .env              # 환경변수 (Webhook URL 등)
├── config.py         # 전역 설정 (User-Agent, 브라우저 옵션 등)
└── main.py           # 실행 파일
```

# 📌Prerequisite

1. 파이썬 3.11.9 받기
    1. 작성일 기준 3.14까지 나와있지만 호환성&안정성 때문에
    2. https://www.python.org/downloads/release/python-3119/
    3. 아래로 쭉 내려가서 Recommended 받으면 됨(윈도우 기준)
    
    <img width="1197" height="268" alt="image" src="https://github.com/user-attachments/assets/73a1d069-677c-4137-8a85-e8d098da62f3" />

    
    설치파일 실행하면 첫 화면에 있는 'Add python.exe to PATH’ 반드시 체크
    
2. 프로젝트 폴더 준비
    1. 폴더 경로에 한글이 섞여 있으면 가끔 에러가 날 수 있음
3. 필수 라이브러리 설치
    1. 폴더 주소창에 cmd 치고 엔터
        1. 파이썬 다른 버전 없다고 가정하고 작성했습니다.
        다른 버전이 있으면 명령어 다름. ←이런 분들은 알아서 잘 하실거라고 믿어요.
            1. ex) py -3.11 -m pip install …
    2. pip install -r requirements.txt
    3. patchright install
4. 환경 설정 파일 만들기 (.env)
    1. 폴더 안에 새 텍스트 문서 만들고 이름을 .env로 변경
    2. 일단 WEBHOOK_URL= 이렇게만 써놓고 저장
5. 파이썬과 구글시트 연결
    
    <img width="699" height="264" alt="image" src="https://github.com/user-attachments/assets/11908b61-9666-4602-8280-51b8882fd877" />
    <details>
    <summary>google apps script 코드</summary>
    <div markdown="1">
      
      ```jsx
      function doPost(e) {
        var incomingData;
        try {
          var params = JSON.parse(e.postData.contents);
          incomingData = params.data;
        } catch (err) {
          return createJSONOutput("error", "JSON Parse Error");
        }
      
        if (!incomingData || incomingData.length === 0) {
          return createJSONOutput("no_data", "No data received");
        }
      
        var sourceGroups = {};
        for (var i = 0; i < incomingData.length; i++) {
          var item = incomingData[i];
          var source = item["수집출처"] || "기타";
          if (!sourceGroups[source]) sourceGroups[source] = [];
          sourceGroups[source].push(item);
        }
      
        var lock = LockService.getScriptLock();
        if (!lock.tryLock(30000)) { // 30초 대기
          return createJSONOutput("busy", "Server is busy");
        }
      
        try {
          var ss = SpreadsheetApp.getActiveSpreadsheet();
          for (var sourceName in sourceGroups) {
            writeToSheetFast(ss, sourceName, sourceGroups[sourceName]);
          }
          return createJSONOutput("success", "Processed " + incomingData.length + " items");
        } catch (e) {
          return createJSONOutput("error", e.toString());
        } finally {
          lock.releaseLock();
        }
      }
      
      function writeToSheetFast(ss, sheetName, data) {
        var sheet = ss.getSheetByName(sheetName);
        var cache = CacheService.getScriptCache();
        var cacheKey = "HEADER_" + sheetName;
        
        if (!sheet) {
          sheet = ss.insertSheet(sheetName);
        }
      
        var headers = [];
        var headerMap = {};
        var cachedHeaders = cache.get(cacheKey);
        var lastRow = sheet.getLastRow();
      
        if (lastRow === 0) {
          headers = ["기업명", "대표자명", "고유키", "수집출처"];
          sheet.appendRow(headers);
          cache.put(cacheKey, JSON.stringify(headers), 21600);
        } else if (cachedHeaders) {
          headers = JSON.parse(cachedHeaders);
        } else {
          var lastCol = sheet.getLastColumn();
          if (lastCol > 0) {
            headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
          } else {
            headers = ["기업명", "대표자명", "고유키", "수집출처"];
            sheet.appendRow(headers);
          }
          cache.put(cacheKey, JSON.stringify(headers), 21600);
        }
      
        headers.forEach(function(h, i) { headerMap[h] = i; });
      
        var newHeaders = [];
        data.forEach(function(item) {
          for (var key in item) {
            if (!headerMap.hasOwnProperty(key) && newHeaders.indexOf(key) === -1) {
              newHeaders.push(key);
            }
          }
        });
      
        if (newHeaders.length > 0) {
          sheet.getRange(1, headers.length + 1, 1, newHeaders.length).setValues([newHeaders]);
          newHeaders.forEach(function(h) {
            headers.push(h);
            headerMap[h] = headers.length - 1;
          });
          cache.put(cacheKey, JSON.stringify(headers), 21600);
        }
      
        var newRows = data.map(function(item) {
          var row = new Array(headers.length).fill("");
          for (var k in item) {
            if (headerMap.hasOwnProperty(k)) {
              row[headerMap[k]] = item[k];
            }
          }
          return row;
        });
      
        if (newRows.length > 0) {
          sheet.getRange(sheet.getLastRow() + 1, 1, newRows.length, headers.length).setValues(newRows);
        }
      }
      
      function createJSONOutput(result, msg) {
        return ContentService.createTextOutput(JSON.stringify({
          "result": result,
          "msg": msg
        })).setMimeType(ContentService.MimeType.JSON);
      }
      ```

    </div>
    </details>

        
    1. code.gs에 위의 코드 입력
    2. 배포 → 새 배포
    3. 유형선택 톱니바퀴 클릭 → 웹 앱 선택
    4. ‘다음 사용자 인증 정보로 실행’: 건드리지 않음
    5. ‘액세스 권한이 있는 사용자’: 나만 → 모든 사용자
    6. 액세스 승인 해주면 됨 (무서운 경고창이 나와도 승인)
    7. 배포 후 웹 앱 URL 복사
        1. ex) https://script.google.com/macros/s/배포ID값/exec
    8. .env 파일의 뒤에 붙여넣기
    
    ```jsx
    WEBHOOK_URL=https://script.google.com/macros/s/배포ID값/exec
    ```
    
6. 코드 에디터 설치
    1. VS code 추천
        1. https://blowingnose.tistory.com/37
7. PC 절전 모드 해제

# 📌AI에게 내 코드 첨부하는 방법

개별 코드 파일은 그냥 드래그&드랍으로 된다.

폴더 구조를 유지하고 싶다면 아래의 방법 참고.

단, 질문 내용과 상관 없는 파일이 많으면 많을수록 답의 질이 떨어짐

### 제미나이

유료만 가능.

<img width="799" height="405" alt="image" src="https://github.com/user-attachments/assets/2cebc981-5900-423b-8fb1-1e9dd97647c1" />

<img width="503" height="251" alt="image" src="https://github.com/user-attachments/assets/89100b75-af77-47b0-85b9-98ae6d03b340" />

순서대로 + 버튼, 코드 가져오기, 폴더 업로드 눌러서 내 코드들이 들어가있는 폴더를 첨부하면 된다.

단, 폴더 크기가 100MB를 넘어가면 첨부되지 않는다.

깃헙 레포 가져오는 것도 된다.(특정 브랜치 바라보게 하는 것도 가능)

깃헙 레포도 너무 크면 첨부 안 된다.

### GPT & 클로드

1. 내가 첨부하고 싶은 폴더를 압축한다.
2. 채팅창에 드래그&드랍

# 📌새로운 사이트 추가하기

### 설정 파일의 원리

우리 크롤러는 `configs` 폴더 안에 있는 `.json` 파일들을 읽어서 작동함 새로운 사이트를 수집하려면 이 폴더에 파일만 하나 추가하면 됨. 간혹 json 파일만으로 안 될 만한 보안 레벨이 높은 사이트는 hook 코드를 추가로 구현해야 함.

<details>
<summary>json 예시</summary>
<div markdown="1">

  ```jsx
  //Json은 주석 기능 없어서 주석 다 지워야 함
  {
    // [기본 정보]
    "name": "새로운사이트",          // 로그에 표시될 이름
    "domain_group": "new_site",    // 중복 방지용 ID (영문 권장)
    "type": "html",                // "html"(기본) 또는 "browser"(복잡한 사이트)
    
    // [고급 설정] (생략 가능)
    "deep_crawl": "true",          // 홈페이지 주소 있으면 심층 크롤링 할지 (기본 False)
    "concurrency": 3,              // [속도] 한 번에 몇 페이지씩 긁을지 (기본 3, 너무 높이면 차단됨)
    "hooks_file": "",              // [특수기능] "hooks/파일명.py" (로그인 등 파이썬 코드가 필요할 때만 작성)
  
    // [요청 설정]
    "request": {
      "url": "https://www.site.com/list.php",
      "method": "GET",             // "GET" 또는 "POST"
      
      // [파라미터] 주소 뒤에 붙는 값 (?key=value)
      "params": {
        "Page": "{page}",          // 페이지 번호가 들어갈 자리
        "searchType": "all"
      },
      
      // [데이터] POST 전송 시 필요한 값 (GET일 땐 비워둠)
      "data": {}, 
  
      // [페이지 넘김 규칙]
      "pagination": {
        "param": "Page",           // params 안에서 페이지 번호에 해당하는 키 이름. 이거 못 찾으면 type을 browser로 해야함.
        "start": 1,                // 시작 페이지
        "max_page": 100,           // 끝 페이지
        "step": 1                  // 몇 페이지씩 건너뛸지
      },
  
      // [브라우저 액션] type이 "browser"일 때만 작동 (클릭, 대기 등)
      "actions": [
        // { "type": "wait", "selector": "table.list" },    // 로딩 대기
        // { "type": "click", "selector": "button.more" },  // 더보기 클릭
        // { "type": "sleep", "seconds": 2 }                // 2초 대기
      ]
    },
  
    // [데이터 추출 설정]
    "extraction": {
      "strategy": "css",           // "css" (기본값)
      "smart_extraction": false,   // true로 하면 스마트 추출 시도 (실험적 기능)
      "base_selector": "tr.list_item", // [필수] 리스트의 한 줄(Row) 선택자
      
      "fields": {
        "기업명": "td.company",
        "대표자명": "td.ceo",
        "전화번호": "td.tel",
        "_raw_html": "self > inner_html" // hooks 처리가 필요할 때 원본 보관용
      }
    }
  }
  ```

</div>
</details>
    

### 권장 방법: 제미나이/GPT/클로드

1. ai에게 내 코드 폴더 전체를 준다
2. 수집을 원하는 페이지 소스를 준다
    1. 원하는 페이지에서 Ctrl U
    2. 전체 복붙
3. 페이지 넘겨가면서 바뀌는 걸 체크
    1. GET 메서드는 주소가 바뀔 거고
    2. POST 메서드는 f12 눌러서 오가는 파일 찾아야 함
    3. 페이지 넘버링 조절하는 파라미터 찾기
4. 1페이지 주소, 메서드, 바로 위에서 찾은 파라미터, 총 페이지 수 정리해서 준다

이렇게 하면 알아서 코드 짜줄 것임

### 만약! http나 api가 아닌 browser type으로 크롤링 해야한다면?

core/network.py의 AsyncFetcher 클래스의 _fetch_browser 함수 안에 브라우저를 이용한 크롤링에 필요한 기능들이 들어가 있다.

<details>
<summary>코드</summary>
<div markdown="1">

```python
  if act_type == 'wait':
      await page.wait_for_selector(selector, state='visible', timeout=10000)
  elif act_type == 'click':
      await page.click(selector, delay=random.randint(100, 300))
      await asyncio.sleep(random.uniform(0.5, 1.5))
  elif act_type == 'sleep':
      await asyncio.sleep(action.get('seconds', 1))
  elif act_type == 'input':
      await page.fill(selector, action.get('value'))
  elif act_type == 'press':
      key = action.get('key')
      await page.keyboard.press(key)
      await asyncio.sleep(random.uniform(0.2,0.5))
  elif act_type == 'mouse_move':
      try:
          element = await page.wait_for_selector(selector, state='visible', timeout=5000)
          box = await element.bounding_box()
          
          if box:
              target_x = box['x'] + box['width'] / 2 + random.uniform(-5, 5)
              target_y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
              
              await page.mouse.move(target_x, target_y, steps=random.randint(30, 60))
      except Exception as e:
          self.logger.warning(f"Mouse move failed: {e}")
  ```

</div>
</details>
    
    
<details>
<summary>json에서 사용방법</summary>
<div markdown="1">

  ```jsx
      "actions": [
        { "type": "wait", "selector": "xpath=//*[contains(text(), '정상')]" },
        { "type": "click", "selector": "xpath=(//*[contains(text(), '정상')])[last()]/preceding::input[@type='checkbox'][1]" },
        { "type": "click", "selector": "xpath=(//*[contains(text(), '소기업')])[last()]/preceding::input[@type='checkbox'][1]" },
        { "type": "click", "selector": "xpath=(//*[contains(text(), '개인사업자')])[last()]/preceding::input[@type='checkbox'][1]" },
        { "type": "sleep", "seconds": 2 },
        { "type": "mouse_move", "selector": "xpath=//button[contains(., '조회하기')]" },
        { "type": "hover", "selector": "xpath=//button[contains(., '조회하기')]" },
        { "type": "sleep", "seconds": 0.5 },
        { "type": "click", "selector": "xpath=//button[contains(., '조회하기')]" },
        { "type": "wait", "selector": "div.result-txt-wrap" },
        { "type": "click", "selector": "#pageCount" },
        { "type": "press", "key": "ArrowDown" },
        { "type": "press", "key": "ArrowDown" },
        { "type": "press", "key": "ArrowDown" },
        { "type": "press", "key": "Enter" },
        { "type": "wait", "selector": "div.result-txt-wrap" },
        { "type": "sleep", "seconds": 1 }
      ],
  ```

</div>
</details>
    

    

지금 들어가 있는 기능은 몇 개 안 돼서 지원하지 않는 기능은 추후에 따로 작성해서 넣어줘야 한다.

새로운 act_type 추가도 웬만하면 ai가 할루시네이션 없이 짜줌.

# 📌실행 및 결과 확인

1. 크롤러 실행하기
    1. VS code를 설치하고 extension까지 설치했다면 오른쪽 위에 실행 버튼 생김. 실행.
    2. 로그 확인
    - `🚀 Start Crawling...` (시작됨)
    - `Page 1: Extracted 10 items` (수집 중)
    - `✅ Sent 10 items` (구글 시트로 전송 성공)
2. 구글 시트 확인
    - 크롤러가 `Sent` 메시지를 띄우면, 1~2초 뒤에 연결해둔 구글 시트에 데이터가 들어옴
3. 종료
    - ctrl C 한 번 누르면 수집 종료 됨
    - 버퍼에 담아놓은 데이터들이 전부 전송되면 완전히 종료 됨

# 📌CSS selector 팁

| **기호** | **설명** | **예시** | **해석** |
| --- | --- | --- | --- |
| **`.`** | 클래스 (Class) | `.tit_view` | `class="tit_view"`인 요소 |
| **`#`** | 아이디 (ID) | `#login_btn` | `id="login_btn"`인 요소 (페이지에 딱 하나) |
| **`>`** | 직계 자식 | `div > a` | div 바로 아래에 있는 a (손자는 포함 안 됨) |
| **(공백)** | 후손 (자식 포함) | `div a` | div 안에 있는 모든 a (손자, 증손자 다 포함) |
| **`[]`** | 속성값 | `input[name='id']` | name 속성이 'id'인 input 태그 |
| **`:`** | 상태/순서 | `tr:nth-child(2)` | 2번째 줄(tr) |
- **❌ 나쁜 예 (너무 김, 깨지기 쉬움)**
    - `body > div.wrap > div.container > div.content > table > tbody > tr:nth-child(2) > td.name`
    - *이유: 중간에 `div` 하나만 더 생겨도 못 찾음.*
- **✅ 좋은 예 (핵심만 콕 집음)**
    - `table.list_table td.name`
    - *해석: `list_table`이라는 클래스를 가진 테이블 안에 있는 `name` 클래스 칸을 다 가져와라.*

**Q. 클래스 이름에 공백이 있어요! `class="company name"`**

- **A.** 공백은 점(`.`)으로 채우면 됩니다.
    - `.company.name`

**Q. ID 뒤에 숫자가 계속 바뀌어요. `#view_12938`, `#view_99123`**

- **A.** 뒤에 숫자를 버리고 앞부분만 일치하는 걸 찾으세요. (`^=` : ~로 시작함)
    - `div[id^='view_']`

**Q. 버튼이 3개인데 다 똑같이 생겼어요.**

- **A.** 속성값이나 순서를 이용하세요.
    - 글자가 포함된 걸 찾기: `button:contains('검색')` (참고: 표준 CSS 아님, jQuery/Playwright용)
    - 특정 속성 이용: `button[type='submit']`
    - 순서 이용: `div.btns > button:nth-child(1)` (첫 번째 버튼)

# 📌수집 실패

웬만하면 디버깅도 ai 돌리는 게 쉽고 빠름.

### skipped

- 코드는 잘 돌아가는데 skipped가 0이 아니라면 중복 체크 검사에 걸려서 구글 시트로 전송이 안 되고 있는 것.
- states 폴더 아래에 있는 db 삭제하면 전송 됨. 테스트 목적이 아니면 지우지 않는 걸 추천.
- 구글 시트에서는 중복 체크 안 하므로, 이미 추가되었던 데이터도 또 다시 시트 아래에 추가된다.

### 1페이지만 new, 나머지는 skipped

- post 메서드에서만 나는 버그. 자꾸 1페이지로 가지는 것.
- 보통 수준의 사이트는 문제 없이 될 거지만, 크롤링에 대해 엄격한 사이트는 이 오류가 뜰 수 있음.
browser 타입으로 하거나 엔진 코드 수정해야 함

### 컴파일 오류

- 아마도 json 파일을 잘못 만들었을 확률이 높음

### 429 Error

- 너무 많이 요청 보내는 거라 concurrency 낮춰야 함

### IP 차단

- 직접 홈페이지 들어가보고 안 들어가지면 IP 차단당한 것임.
- 원래는 이 위험때문에 프록시 돌려야 하는데, 무료 프록시는 이미 차단해놓은 사이트가 꽤 있고, 웬만하면 유료임

### GAS busy

- google apps script에 요청이 많이 쌓여서 튕겨져 나온 상태. 알아서 재시도 할 것임

### AttributeError: NoneType…

- CSS 선택자가 틀림

### browser 타입

- 사이트별로 보안 레벨, 구조, 접근 방식이 다 다름.
- 유지보수성이 좋지 않으므로 최대한 안 쓸 수 있게 노력해야함.

# 📌기업 홈페이지 접속

만약 수집하는 사이트에 기업 홈페이지 주소가 기재되어 있다면, 홈페이지로 접속해서 전화번호, 팩스번호, 메일주소를 수집 “시도”하는 기능이 있다. 이 기능을 켜면 속도가 많이 느려진다.

기능을 키려면 json 파일에서 deep_crawl 변수를 true로 놓으면 된다.
