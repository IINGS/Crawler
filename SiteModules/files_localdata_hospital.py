import xml.etree.ElementTree as ET
from crawler_base import BaseFileCrawler

class HospitalFileCrawler(BaseFileCrawler):
    def __init__(self):
        # 1. group_name: "localdata_hospital" (DB 파일명 및 체크포인트 키)
        # 2. source_name: "병원정보_파일" (GAS 전송 시 출처 표기)
        # 3. target_folder: "localdata_hospital" (FilesToParse 아래의 폴더명)
        super().__init__("localdata_hospital", "LOCALDATA", "localdata_hospital")

    def process_single_file(self, file_path):
        batch = []
        count = 0
        
        # iterparse: 대용량 XML을 한 줄씩 읽어 메모리 폭증 방지
        context = ET.iterparse(file_path, events=('end',))
        context = iter(context)

        for event, elem in context:
            if elem.tag == 'row': # <row> 태그가 완성될 때마다 처리
                
                # [Helper] 태그 텍스트 추출 (없으면 빈 문자열)
                def get(tag):
                    found = elem.find(tag)
                    return found.text.strip() if found is not None and found.text else ""

                # 1. 필터링: 영업상태코드(trdStateGbn)가 '01'(영업/정상)이 아니면 패스
                if get('trdStateGbn') != '01':
                    elem.clear() # 메모리 비우기 (중요)
                    continue

                # 2. 데이터 매핑
                # 요청하신 9열(업태), 10열(인허가일자) 매핑
                extra_data = {
                    "업태 구분명": get('uptaeNm'),
                    "인허가일자": get('apvPermYmd'),
                    "전화번호": get('siteTel')
                }

                # 대표자명은 공백(""), 기업명 매핑
                record = self.processor.create_record(get('bplcNm'), "", extra_data)

                # 3. 중복 체크 (로컬 DB 활용)
                if self.state.is_new_or_changed(record['고유키'], record):
                    batch.append(record)
                    count += 1

                # 4. 메모리 해제 (처리한 행은 즉시 삭제)
                elem.clear()

                # 5. 배치 전송 (200건 쌓이면 전송)
                if len(batch) >= 200:
                    self.processor.send_to_gas(self.smart_engine.process_batch(batch))
                    batch = []

        # 남은 데이터 털어내기
        if batch:
            self.processor.send_to_gas(self.smart_engine.process_batch(batch))

        self.log(f"▷ {count}건 처리 완료")