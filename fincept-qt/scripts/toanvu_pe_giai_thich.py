"""Nội dung giải thích cho tab "Vùng P/E × Lãi suất · Toàn Vũ" (stdlib, chỉ dữ liệu).

Soạn 06/10/2026 bằng quy trình 3 bản nháp (người mới / PM bận / chuẩn kỹ thuật) → tổng hợp có đối chiếu code
(toanvu_pe_build.py, toanvu_pe_sau.py) → 2 người phản biện (người đọc không chuyên, người kiểm sai) → sửa.
Trang dùng qua toanvu_pe_trang.doc_hieu_sections() và apply_guides().

- buoc[*].vi_du và thuat_ngu[*].vi_du là MẪU: {ma} {gia} {pe} {pct} {ls} {nguong} {pe_nguong} {gia_nguong} {ey} {erp}
  {pe_fair} {trang_thai} được điền bằng số thật của mã đang xem.
- faq dùng số cố định của HPG phiên 05/10/2026 (NGAY_SO_FAQ); khi dựng lại dữ liệu, các câu trả lời vẫn đúng về
  nghĩa nhưng số ví dụ có thể lệch: soạn lại nếu cần.
"""

NGAY_SO_FAQ = "05/10/2026"
MA_FAQ = "HPG"

NOI_DUNG = {'tom_tat_1_cau': 'Luật của Toàn Vũ (viết tắt TV) coi một cổ phiếu là rẻ khi P/E hôm nay nằm trong nhóm thấp nhất của chính mã đó trong 250 phiên '
                  'gần nhất (khoảng 1 năm), nhóm đó rộng bao nhiêu thì tính từ lãi tiền gửi (LS): với LS 7,60% hiện nay là 29,6% số phiên rẻ nhất, '
                  'LS càng cao thì nhóm càng hẹp, và khi điều kiện này đúng trang gọi là “luật TV bật”.',
 'faq': [{'q': 'Lãi suất Hit là gì?',
          'a': 'Hit là viết tắt của Hit Rate, nghĩa là TỶ LỆ THẮNG, không phải lãi suất. Chữ rate ở đây là tỷ lệ phần trăm, không phải interest rate '
               '(lãi suất), nên “Hit Rate” rất dễ bị đọc thành “lãi suất Hit”. Hit 60 phiên trả lời câu hỏi: trong 100 lần luật TV bật, có bao nhiêu '
               'lần giá 60 phiên sau (khoảng 3 tháng) cao hơn giá hôm đó. Ví dụ HPG: trong 1.748 ngày luật bật đã đủ 60 phiên phía sau để chấm, có '
               '48,3% số ngày giá 3 tháng sau cao hơn, vậy Hit = 48,3%. “Thắng” chỉ có nghĩa giá lên; lên 0,01% cũng tính là thắng. Trang còn có LS '
               '(lãi suất tiền gửi), là ĐẦU VÀO của luật: lãi huy động VND kỳ hạn trên 12 tháng, mức cao nhất, hiện 7,60%/năm. LS là điều kiện, Hit '
               'là kết quả. Hai chữ này hay đứng sát nhau trên biểu đồ, ví dụ nhãn “LS 8–10% · hit 68,5%”: đọc là trong những ngày luật bật lúc LS '
               'đang ở khoảng 8–10%, có 68,5% số ngày giá 60 phiên sau cao hơn (đếm theo từng ngày của từng mã, các ngày liền nhau dùng chung đường '
               'giá, chưa trễ EPS).'},
         {'q': 'Luật TV bật nghĩa là gì?',
          'a': 'Bật (trang còn gọi là kích hoạt, có tín hiệu; TV gọi là Signal = BUY) nghĩa là P/E hôm nay của mã nằm trong nhóm rẻ nhất của chính '
               'mã đó trong 250 phiên gần nhất, và nhóm đó rộng bao nhiêu thì tính từ LS. Ví dụ HPG phiên 05/10/2026: P/E 7,45 lần; trong 250 phiên '
               'chỉ có 7 phiên P/E bằng hoặc thấp hơn, 7 ÷ 250 = 2,8%, viết gọn P3. LS 7,60% cho ngưỡng 29,6%. 2,8 ≤ 29,6 nên luật bật. Nếu P/E lên '
               'tới khoảng 9,42 lần trở lên (giá khoảng 25.910đ, lợi nhuận 4 quý giữ nguyên) thì luật tắt. Bật chỉ là bộ lọc “rẻ so với chính nó”, '
               'không phải lệnh mua: sau khi bỏ lỗi nhìn trước EPS, những ngày luật bật có Hit 50,6%, còn một ngày bất kỳ là 51,8%, tức riêng việc '
               'bật không cho kết quả tốt hơn mua vào một ngày bất kỳ.'},
         {'q': 'Hit trên 50% có nghĩa là lời hơn gửi tiết kiệm không?',
          'a': 'Không. Hit chỉ hỏi giá có lên hay không, không hỏi lên đủ chưa. Gộp cả gần 400 mã (không phải chỉ số VN-Index): những ngày luật bật '
               'có Hit 52,0%, một ngày bất kỳ có Hit 51,8%. Chênh 0,2 điểm, tức luật bật hay không gần như không đổi khả năng giá lên sau 3 tháng. '
               'Muốn hỏi “có lời hơn tiền gửi không” thì phải so với rào tiền gửi: LS của chính ngày mua × 60 ÷ 250 (một năm khoảng 250 phiên). Với '
               'LS hôm nay 7,60% rào là khoảng 1,82%; ví dụ ở năm LS 12% thì rào là 2,88%. Tính trên toàn lịch sử, mỗi ngày dùng LS của ngày đó: chỉ '
               '47,1% số ngày luật bật lời nhiều hơn tiền lãi gửi tiết kiệm cùng kỳ; với HPG là 43,4%. Từ mới: vượt lãi tiền gửi (xem Thuật ngữ).'},
         {'q': 'Vì sao HPG có nhiều con số Hit khác nhau (48,3%, 57,4%, 22,2%...)?',
          'a': 'Cùng là tỷ lệ thắng 60 phiên khi luật bật, nhưng đếm theo cách khác nhau. Một: từng ngày bật, cách TV, 48,3% trên 1.748 ngày đã đủ '
               '60 phiên phía sau. Hai: từng ngày, chỉ dùng lợi nhuận đã công bố, 45,4%. Ba: theo mốc độc lập, 57,4% trên 47 mốc. Lý do phải đếm '
               'mốc: hai ngày bật liền nhau dùng chung 59/60 phiên giá phía sau nên kết quả gần như y hệt; đếm từng ngày giống hỏi một người 60 lần '
               'rồi gọi là khảo sát 60 người. Kiểm định lấy ngày bật đầu tiên làm mốc, mốc sau phải cách ít nhất 60 phiên. Hit theo mốc cao hơn theo '
               'ngày nghĩa là những ngày bật không được chọn làm mốc có tỷ lệ thắng thấp hơn; hai số không mâu thuẫn, chỉ đếm khác nhau. Với 47 mốc, '
               'phần vượt mọi mã cùng ngày +2,83 điểm vẫn có thể do may (p 0,23), nên chưa thể nói luật hiệu quả với HPG. Bảng Thắng 60 (co) ghi 46 '
               'mốc, 56,5% vì bỏ thêm ngày chưa đủ 60 phiên P/E để tính percentile; chênh 1 mốc không đổi kết luận. Bốn: chỉ những lần bật đúng lúc '
               'LS tăng mạnh như hiện nay, không nhìn trước EPS, 2/9 mốc = 22,2%, hiệu chỉnh về rổ (co) còn 32,6%. Con số sát nhất với câu hỏi “bây '
               'giờ thì sao” là con số cuối. Từ mới: mốc độc lập, nhìn trước EPS, p, co (xem Thuật ngữ).'},
         {'q': 'HPG đang bật luật TV và được chấm “Hội tụ mạnh”, vậy có phải nên mua?',
          'a': 'Không, và trang không gán hành động mua/bán. “Bật” chỉ nói P/E hôm nay (7,45 lần) nằm trong nhóm rẻ nhất của chính HPG trong 1 năm '
               '(P3, dưới ngưỡng P29,6); nó không nói HPG rẻ so với ngành hay chu kỳ dài, và TV tự ghi cần thêm tín hiệu từ biểu đồ giá (phân tích '
               'kỹ thuật) trước khi vào lệnh. “Hội tụ mạnh” đếm xem sáu nguồn có cùng chiều không: TV +1 (đang rẻ so với chính nó); HHP +1 (P/B '
               '1,23, thấp hơn mức trung bình 1,78 của chính HPG từ 12/2017, tức −1,10σ); ERP +1 (+5,81); EPS +1 (EPS FY2026 đồng thuận +64%: trung '
               'bình dự báo của các công ty chứng khoán là lợi nhuận mỗi cổ phiếu năm 2026 tăng 64%); Chủ thể +1 (người nội bộ và cổ đông lớn mua '
               'ròng 0,39% số cổ phiếu trong 12 tháng); Lịch sử 0 (p 0,23); cộng 5 điểm. Điểm TV +1 không có nghĩa luật đã được chứng minh hiệu quả. '
               'Cột “Thắng 60 (co)” hỏi chuyện khác: những lần luật bật ĐÚNG lúc LS đang tăng mạnh như bây giờ (+0,6 điểm trong 6 tháng), bản không '
               'nhìn trước EPS, HPG chỉ thắng 2/9 mốc (22,2%); hiệu chỉnh về rổ còn 32,6%, thấp xa mức 55,7% (cũng đã hiệu chỉnh) của mọi thời điểm. '
               'Rẻ mà LS đang đi lên là điều kiện bất lợi trong lịch sử. Từ mới: σ HHP, ERP, mức hội tụ, co (xem Thuật ngữ).'},
         {'q': 'Vì sao trang dùng LS 7,60% và ngưỡng 29,6, còn báo cáo TV ghi 11,78% và 13?',
          'a': 'Tệp FiinProX TV dùng xếp số MỚI NHẤT lên đầu. Bản gốc lấy dòng cuối tệp làm “hiện tại”, nhưng dòng cuối lại là số CŨ NHẤT: 11,78% '
               'của ngày 03/03/2008. Số mới nhất là 7,60% (31/08/2026), cũng là số báo cáo vĩ mô của chính TV dùng. Thay vào công thức: 40 − 4 × '
               '(7,60 − 5) = 29,6. Ngưỡng 29,6 dễ đạt hơn nhiều so với 13: mã chỉ cần nằm trong nhóm 29,6% số phiên rẻ nhất năm thay vì 13%. Phiên '
               '05/10/2026 trang đếm được 249 trên 376 mã có đủ dữ liệu P/E để chấm đang bật. Bản TV in 259/368 mã, nhưng số đó không khớp với chính '
               'ngưỡng 13 TV ghi, nên đừng so hai con số này với nhau. Tệp dừng ở 31/08/2026 nên trang giữ 7,60% đến khi có số mới. Từ mới: '
               'percentile, ngưỡng X (xem Thuật ngữ).'},
         {'q': '“Nhìn trước EPS” là gì, sao nó làm luật mất lợi thế?',
          'a': 'Chuỗi P/E lịch sử của Bloomberg ghi lợi nhuận quý mới vào đúng ngày cuối quý (khoảng 95% số lần EPS đổi rơi vào 31/3, 30/6, 30/9, '
               '31/12), trong khi BCTC quý ra sau đó 3 đến 7 tuần. Nên trong dữ liệu, một mã sắp báo lãi tăng mạnh đã trông “rẻ” trước khi nhà đầu '
               'tư thật biết: tín hiệu thắng nhờ biết trước. Bản trễ 45 ngày xấp xỉ việc chỉ dùng lợi nhuận đã công bố: ở ngày t, P/E tính bằng EPS '
               'của 45 ngày trước (hạn nộp BCTC hợp nhất quý). Đây là quy ước chung cho mọi mã, không phải ngày công bố thật của từng mã. Kết quả '
               'gộp gần 400 mã: phần vượt mọi mã cùng ngày từ +1,13 còn +0,22 điểm %, Hit khi bật còn 50,6%, thấp hơn 51,8% của một ngày bất kỳ (mua '
               'không cần luật), alpha kiểu TV từ +0,16 thành −0,77. Ở HPG, Hit theo ngày từ 48,3% còn 45,4%. Từ mới: vượt cùng ngày, alpha, điểm % '
               '(xem Thuật ngữ).'}],
 'buoc': [{'so': '1',
           'tieu_de': 'Hai công cụ của TV, và mốc so sánh LS',
           'text': 'Toàn Vũ (TV) có hai công cụ, đừng trộn. Công cụ A là luật từng mã (TV gọi là Dream-RSI dù không dùng chỉ báo RSI; báo cáo tên '
                   '“Per-Stock ERP Backtest” nhưng luật không dùng ERP): hỏi P/E hôm nay có rẻ so với 1 năm của chính mã không, độ khắt khe tùy LS, '
                   'kết quả là bật hoặc không (bước 2 đến 4). Công cụ B là khung vĩ mô: đặt lợi nhuận của cả rổ VN-Index cạnh lãi tiền gửi để xếp '
                   'thị trường vào các vùng (bước 5). Bước 6 là phần kiểm lại. Cả hai dùng chung LS: lãi huy động VND kỳ hạn trên 12 tháng, mức cao '
                   'nhất trong bảng FiinProX, cập nhật mỗi tháng một lần. Ở công cụ A, LS chỉ làm một việc là chỉnh độ khắt khe của chuẩn “rẻ”; luật '
                   'không so lợi suất của mã với tiền gửi.',
           'vi_du': 'Hôm nay LS = {ls}%: gửi 100 triệu kỳ hạn trên 12 tháng ở mức lãi cao nhất nhận khoảng {ls} triệu mỗi năm, gần như không rủi '
                    'ro.'},
          {'so': '2',
           'tieu_de': 'Hỏi: P/E hôm nay có thấp so với 1 năm của chính mã?',
           'text': 'Lấy P/E hôm nay (giá ÷ lợi nhuận 4 quý gần nhất), xếp chung với P/E của 250 phiên gần nhất của CHÍNH mã đó (khoảng 1 năm, cần ít '
                   'nhất 60 phiên có P/E). Percentile là % số phiên có P/E bằng hoặc thấp hơn hôm nay, viết gọn bằng chữ P: P3 là sát đáy năm, P50 '
                   'là giữa, P90 là sát đỉnh. TV so mỗi mã với chính nó, không so ngân hàng với thép.',
           'vi_du': '{ma} giá {gia}đ, P/E {pe} lần. Xếp P/E của 250 phiên gần nhất từ thấp tới cao: khoảng {pct}% số phiên có P/E bằng hoặc thấp hơn '
                    'hôm nay, viết gọn là P{pct}. Số càng nhỏ càng sát đáy của năm.'},
          {'so': '3',
           'tieu_de': 'Từ LS tính chuẩn “rẻ” (ngưỡng X)',
           'text': 'Ngưỡng X = 40 − 4 × (LS − 5), nhưng không bao giờ thấp hơn 5. Mỗi 1 điểm LS tăng thêm, ngưỡng hẹp lại 4 điểm: LS 5% thì X = 40; '
                   'LS 7,60% thì 40 − 4 × 2,60 = 29,6; LS 10% thì X = 20; LS 15% thì ra 0, thấp hơn 5 nên lấy 5. Lý do theo TV: LS càng cao thì gửi '
                   'tiết kiệm càng hấp dẫn, nên cổ phiếu phải rẻ hơn hẳn mới đáng đổi. Lưu ý: ngưỡng chỉ quyết định luật dễ bật hay khó bật, không '
                   'kiểm tra cổ phiếu có thật sự sinh lời hơn tiền gửi; việc so thẳng với tiền gửi là của ERP ở bước 5, nên có mã đang bật mà ERP âm '
                   '(rẻ so với chính nó, vẫn đắt so với tiền gửi). Ngưỡng chỉ dùng MỨC LS, không xét LS đang lên hay xuống.',
           'vi_du': 'Với LS {ls}%: X = 40 − 4 × ({ls} − 5), không thấp hơn 5, ra {nguong}, viết gọn P{nguong}. P/E hôm nay phải nằm trong nhóm '
                    '{nguong}% số phiên rẻ nhất năm qua thì mới tính là rẻ.'},
          {'so': '4',
           'tieu_de': 'So hai số: luật bật hay không, giá ngưỡng ở đâu',
           'text': 'Luật TV bật (trang còn gọi là kích hoạt hoặc có tín hiệu; TV gọi là Signal = BUY) khi percentile ≤ X. Chỉ vậy thôi: luật không '
                   'xét xu hướng giá, ngành, ERP hay tin tức. Đổi ngưỡng ra P/E và ra giá cho dễ nhìn: P/E phải thấp hơn mức nào thì luật còn bật, '
                   'và với lợi nhuận 4 quý hiện tại thì mức đó ứng với giá bao nhiêu. Bật nghĩa là “rẻ so với chính nó theo chuẩn TV”, không phải '
                   'lệnh mua.',
           'vi_du': '{ma}: percentile {pct} so với ngưỡng {nguong} → luật TV {trang_thai}. Luật bật khi P/E thấp hơn khoảng {pe_nguong} lần, tương '
                    'ứng giá dưới khoảng {gia_nguong}đ nếu lợi nhuận 4 quý và LS giữ nguyên.'},
          {'so': '5',
           'tieu_de': 'Công cụ thứ hai của TV, cho cả thị trường: EY, P/E hòa tiền gửi, ERP',
           'text': 'Đây là khung vĩ mô TV dùng cho cả VN-Index; luật từng mã không dùng nó, trang tính thêm cho từng mã để đối chiếu. EY = 100 ÷ '
                   'P/E, gọi là lợi suất lợi nhuận: cứ 100 đồng bỏ ra mua cổ phiếu thì công ty làm ra bao nhiêu đồng lợi nhuận một năm; EY không '
                   'phải lãi suất, cũng không phải cổ tức, chỉ đổi P/E sang cùng đơn vị %/năm để đặt cạnh LS. P/E hòa tiền gửi (TV gọi là P/E fair) '
                   '= 100 ÷ LS: mức P/E mà EY đúng bằng LS, không phải giá mục tiêu. ERP (phần bù cho việc giữ cổ phiếu thay vì gửi tiết kiệm) = EY '
                   '− LS. Mốc của TV: từ +5 là vùng mua mạnh nhất, +2 đến +5 tích lũy, đường 0 là ranh giới hòa với tiền gửi, −3 là ngưỡng nguy '
                   'hiểm; trang gọi 0 đến +2 là “hòa” và dưới 0 là “bất lợi”. Đây là nhãn của TV để đối chiếu báo cáo, không phải khuyến nghị.',
           'vi_du': '{ma}: EY = 100 ÷ {pe} = {ey}%/năm; ERP = {ey} − {ls} = {erp} điểm %; P/E hòa tiền gửi = 100 ÷ {ls} = {pe_fair} lần, so với P/E '
                    'thực {pe} lần.'},
          {'so': '6',
           'tieu_de': 'Chấm điểm bằng lịch sử, rồi kiểm định',
           'text': 'TV chấm mỗi ngày luật bật bằng giá 20, 60, 120 phiên sau (khoảng 1, 3, 6 tháng): Hit là % số lần giá lúc đó cao hơn giá lúc luật '
                   'bật; alpha là lợi suất trung bình khi bật trừ lợi suất trung bình mọi ngày của cùng mã. Hội đồng (nhóm phân tích dựng trang này, '
                   'độc lập với TV) chạy lại luật trên đúng dữ liệu TV gửi rồi kiểm thêm bốn lớp: đếm mốc độc lập cách nhau ≥ 60 phiên, so với mọi '
                   'mã cùng ngày, trễ EPS 45 ngày, tách theo hướng LS 6 tháng. Sau bốn lớp này lợi thế chung của luật gần như về 0; trong các biến '
                   'đã kiểm, thứ còn tách được nhóm mã tốt khỏi nhóm kém là ERP của từng mã.',
           'vi_du': 'Cách chấm một lần: nếu ngày luật bật {ma} giá {gia}đ, thì 60 phiên sau (khoảng 3 tháng) giá cao hơn {gia}đ là một lần thắng, '
                    'thấp hơn là một lần thua. Hit = số lần thắng ÷ tổng số lần.'}],
 'thuat_ngu': [{'nhom': 'Lãi suất & định giá',
                'term': 'LS (lãi suất tiền gửi)',
                'nghia': 'Lãi huy động VND kỳ hạn trên 12 tháng, mức cao nhất trong bảng FiinProX, mỗi tháng một số; TV gọi là “LS TG”. Đây là giá '
                         'của sự an toàn: tiền không vào cổ phiếu thì gửi ngân hàng được bao nhiêu. Vì là số tháng nên ngưỡng X đứng yên suốt tháng.',
                'vi_du': 'Mốc mới nhất 31/08/2026: 7,60%. Số 11,78% TV in là dòng 03/03/2008, dòng cũ nhất của tệp (tệp xếp mới nhất lên đầu).',
                'doc': 'LS là đầu vào của luật, không phải kết quả. LS lên thì chuẩn “rẻ” bị siết, P/E hòa tiền gửi hạ, ERP giảm. Lưu ý: FiinProX '
                       'ghi số tháng từ ngày đầu tháng nên backtest có thể biết LS sớm tới 1 tháng; trang đã kiểm bản trễ LS 1 tháng, kết quả gộp '
                       'gần như không đổi (ngày bật Hit 52,2% so với 52,0%).'},
               {'nhom': 'Lãi suất & định giá',
                'term': 'P/E trailing',
                'nghia': 'Giá chia cho lợi nhuận mỗi cổ phiếu (EPS) của 4 quý gần nhất, chuỗi PE_RATIO của Bloomberg: trả bao nhiêu đồng cho 1 đồng '
                         'lợi nhuận một năm. Mã đang lỗ không có P/E và không được chấm.',
                'vi_du': 'HPG phiên 05/10/2026: giá 20.500đ, P/E 7,45 lần, tức EPS ngầm định khoảng 2.750đ.',
                'doc': 'P/E thấp chỉ là rẻ nếu lợi nhuận 4 quý tới không sụp. Chuỗi P/E lịch sử có lỗi nhìn trước EPS (xem nhóm Kiểm định).'},
               {'nhom': 'Lãi suất & định giá',
                'term': 'EY (lợi suất lợi nhuận)',
                'nghia': 'EY = 100 ÷ P/E, đơn vị %/năm: cứ 100 đồng bỏ ra mua cổ phiếu thì công ty làm ra bao nhiêu đồng lợi nhuận một năm. EY không '
                         'phải lãi suất, cũng không phải cổ tức; nó chỉ đổi P/E sang cùng đơn vị với LS để đặt cạnh nhau.',
                'vi_du': 'HPG: 100 ÷ 7,45 ≈ 13,41%/năm. VN-Index cách TV: 100 ÷ 9,16 = 10,92%/năm.',
                'doc': 'EY là lợi nhuận kế toán, không phải tiền về túi; nếu lợi nhuận sắp giảm thì EY thật thấp hơn con số đang thấy.'},
               {'nhom': 'Lãi suất & định giá',
                'term': 'P/E hòa tiền gửi (TV gọi là P/E fair) = 100 ÷ LS',
                'nghia': 'Mức P/E mà tại đó lợi suất lợi nhuận (EY) đúng bằng lãi gửi tiết kiệm; TV gọi cách tính này là Gordon đơn giản.',
                'vi_du': 'LS 7,60% → 13,16 lần. VN-Index cách TV 9,16 lần, thấp hơn mức hòa 30,4%.',
                'doc': 'P/E thực thấp hơn mức này nghĩa là cổ phiếu cho lợi suất lợi nhuận cao hơn tiền gửi, không có nghĩa giá sẽ lên tới đó. LS '
                       '10% thì mức hòa chỉ còn 10 lần.'},
               {'nhom': 'Lãi suất & định giá',
                'term': 'ERP và các mốc +5 / +2 / 0 / −3',
                'nghia': 'ERP (equity risk premium, phần bù cho việc chịu rủi ro khi giữ cổ phiếu thay vì gửi tiết kiệm) = EY − LS, đơn vị điểm %. '
                         'Mốc của TV: từ +5 là vùng mua mạnh nhất, +2 đến +5 tích lũy, đường 0 là ranh giới hòa với gửi tiết kiệm, −3 là ngưỡng nguy '
                         'hiểm. Trang gọi khoảng 0 đến +2 là “hòa” và dưới 0 là “bất lợi”.',
                'vi_du': 'HPG: 13,41 − 7,60 = +5,81 (vùng từ +5). VN-Index cách TV: +3,32 (tích lũy); vùng này từ 2008 có 1.629 ngày, Hit 60 phiên '
                         '58,3% tính theo ngày, nhưng các ngày đó chỉ gom được 48 khối không chồng nhau, nên độ chắc của 58,3% chỉ ngang một mẫu '
                         'khoảng 48 lần (TV in 1.827 ngày và 61%, số tính đến 07/09/2026).',
                'doc': 'Tên vùng là nhãn của TV, không phải khuyến nghị. ERP rổ là nhiệt kế thị trường. Trong các biến trang đã kiểm, ERP từng mã là '
                       'biến còn tách được nhóm tốt khỏi nhóm kém sau khi bỏ nhìn trước EPS (nhóm ERP trên 10 vượt cùng ngày +1,06 điểm %, nhóm dưới '
                       '−3 kém 1,80 điểm %).'},
               {'nhom': 'Lãi suất & định giá',
                'term': 'P/E rổ: ba cách đo',
                'nghia': 'P/E gộp = tổng vốn hoá ÷ tổng lợi nhuận, chỉ tính mã đang có lãi. Cách TV bỏ thêm mọi mã P/E trên 40; đủ mã giữ cả mã P/E '
                         'cao; ngoài họ Vin bỏ VIC, VHM, VRE, VPL.',
                'vi_du': 'VN-Index 05/10/2026: 9,16 / 11,88 / 9,77 lần, ERP +3,32 / +0,82 / +2,64. Bộ lọc TV bỏ 30 mã, 26,0% vốn hoá; riêng VIC (P/E '
                         '82,9 lần) chiếm 21,7%.',
                'doc': 'Chênh 2,5 điểm ERP lớn hơn bề rộng một vùng: đọc ERP rổ thì hỏi trước “đang đo cách nào?”. Câu “thị trường rẻ” đúng với rổ '
                       'bỏ họ Vin, chưa đúng với chỉ số đủ mã.'},
               {'nhom': 'Luật TV',
                'term': 'Percentile P/E 250 phiên (P3, P30)',
                'nghia': 'Trong 250 phiên gần nhất của chính mã (kể cả hôm nay, cần tối thiểu 60 phiên có P/E), bao nhiêu % số phiên có P/E bằng '
                         'hoặc thấp hơn hôm nay. Viết gọn bằng chữ P: P3 là sát đáy năm, P30 là 30% số phiên rẻ bằng hoặc hơn hôm nay.',
                'vi_du': 'HPG: P/E năm qua đi từ 7,29 đến 15,5 lần; chỉ 7/250 phiên có P/E ≤ 7,45 lần → 7 ÷ 250 = 2,8%, đọc gọn P3.',
                'doc': 'Chỉ là “rẻ so với chính nó 1 năm qua”: một mã đắt cả năm vẫn có thể ở P3, và P/E thấp có thể là bẫy nếu lợi nhuận sắp giảm.'},
               {'nhom': 'Luật TV',
                'term': 'Ngưỡng X = 40 − 4 × (LS − 5), không thấp hơn 5',
                'nghia': 'Chuẩn “rẻ cỡ nào mới tính”: mỗi 1 điểm LS tăng thì ngưỡng hẹp 4 điểm percentile; nếu công thức ra dưới 5 thì lấy 5. TV: LS '
                         'càng cao thì tiêu chuẩn “rẻ” càng khắt khe.',
                'vi_du': 'LS 5% → 40; LS 7,60% → 40 − 10,4 = 29,6; LS 10% → 20; LS 11,78% → 12,9 (TV in 13); LS 15% → ra 0, lấy 5.',
                'doc': 'Hiện X = 29,6, viết gọn P29,6. Ngưỡng chỉ quyết định luật dễ hay khó bật, không so cổ phiếu với tiền gửi: hiện 48/249 mã '
                       'đang bật có ERP âm. Kiểm định thấy ngưỡng động này không tốt hơn một ngưỡng cố định có cùng độ phủ.'},
               {'nhom': 'Luật TV',
                'term': 'Tín hiệu / “luật TV bật” / kích hoạt',
                'nghia': 'Bốn tên cho cùng một trạng thái: một mã bật trong ngày khi percentile P/E ≤ X và ngày đó có số LS (từ 03/2008). TV gọi là '
                         '“Signal = BUY”; trang gọi là bật hoặc kích hoạt và không gán hành động.',
                'vi_du': 'HPG: P3 ≤ P29,6 → bật. Phiên 05/10/2026: 249/376 mã chấm được đang bật. Độ phủ (tỷ lệ số mã đang bật trong một ngày) trung '
                         'bình lịch sử là 30,5%.',
                'doc': 'Độ phủ cỡ một phần ba rổ trở lên nên đây chỉ là bộ lọc thô để soi tiếp.'},
               {'nhom': 'Luật TV',
                'term': 'P/E ngưỡng và giá ngưỡng',
                'nghia': 'Ngưỡng percentile đổi ra con số dễ nhìn: luật còn bật khi P/E thấp hơn mức này (cửa sổ 250 phiên gồm 249 phiên trước đó '
                         'cộng chính hôm nay; giữ nguyên LS và EPS 4 quý), cùng với giá tương ứng.',
                'vi_du': 'HPG: P/E ngưỡng 9,42 lần, giá ngưỡng khoảng 25.910đ; giá 20.500đ phải tăng khoảng 26% mới ra khỏi vùng bật.',
                'doc': 'Hai số này đổi khi có BCTC quý mới (EPS đổi), khi cửa sổ 250 phiên trượt thêm, hoặc khi LS tháng mới làm đổi ngưỡng X.'},
               {'nhom': 'Đo kết quả',
                'term': '60 phiên / 120 phiên',
                'nghia': 'Số phiên giao dịch sau ngày mua dùng để chấm kết quả: 60 phiên ≈ 3 tháng, 120 phiên ≈ 6 tháng (một năm khoảng 250 phiên). '
                         'Lợi suất 60 phiên = giá 60 phiên sau ÷ giá hôm mua − 1, chưa trừ phí.',
                'vi_du': 'Ví dụ minh hoạ: mua HPG 20.500đ, 60 phiên sau 22.000đ thì lợi suất ≈ +7,3%; cùng 60 phiên, gửi tiết kiệm 7,60% được khoảng '
                         '1,82%.',
                'doc': 'Mọi con số Hit, trung bình, alpha đều dựng trên hai lợi suất này.'},
               {'nhom': 'Đo kết quả',
                'term': 'Hit (Hit Rate, tỷ lệ thắng) và “Thắng 60”',
                'nghia': 'Hit Rate là TỶ LỆ THẮNG, không phải lãi suất: % số lần giá 60 phiên sau cao hơn giá lúc luật bật (lợi suất 60 phiên '
                         'dương). Hit không đo mức lời và không so với chỉ số hay tiền gửi. Cột “Thắng 60” trên các bảng là cùng đại lượng, nhưng '
                         'đếm trên mốc độc lập thay vì từng ngày như cách TV.',
                'vi_du': 'HPG cách TV: 1.748 ngày bật đã đủ 60 phiên phía sau, Hit 48,3%. Gộp gần 400 mã: ngày bật 52,0%, ngày bất kỳ 51,8%.',
                'doc': 'So Hit với Hit “mọi ngày” cùng cách đếm, không so với 50% suông; Hit cao mà lời nhỏ, lỗ to vẫn có thể thua. Vì sao HPG có '
                       'nhiều con số Hit: xem phần Hỏi đáp.'},
               {'nhom': 'Đo kết quả',
                'term': 'Điểm % và TB',
                'nghia': 'Điểm % là phần chênh giữa hai con số %, không phải lời thêm bấy nhiêu %. TB là viết tắt của trung bình.',
                'vi_du': 'HPG: những ngày luật bật TB lời 2,87% sau 60 phiên, mọi ngày TB lời 6,50%, nên alpha = 2,87 − 6,50 = −3,63 điểm %.',
                'doc': 'Alpha, vượt cùng ngày, ERP đều tính bằng điểm %.'},
               {'nhom': 'Đo kết quả',
                'term': 'Lợi suất trung bình và trung vị',
                'nghia': 'Trung bình: cộng lợi suất mọi lần rồi chia số lần. Trung vị: lần đứng giữa khi xếp từ thấp đến cao, tức kết quả của “lần '
                         'điển hình”.',
                'vi_du': 'HPG, 47 mốc độc lập khi luật bật: trung bình 60 phiên +7,27% nhưng trung vị chỉ +1,44%.',
                'doc': 'Trung bình cách xa trung vị nghĩa là vài lần thắng lớn kéo con số lên; tin trung vị hơn.'},
               {'nhom': 'Đo kết quả',
                'term': 'Alpha (cách TV)',
                'nghia': 'Lợi suất TB 60 phiên những ngày luật bật trừ lợi suất TB 60 phiên của mọi ngày từ 03/2008 (từ khi có số LS), bất kể luật '
                         'bật hay không, của chính mã đó, đơn vị điểm %. TV: alpha dương là tín hiệu có giá trị thực.',
                'vi_du': 'HPG: 2,87% − 6,50% = −3,63 điểm % (bản trễ EPS: −4,70). Gộp gần 400 mã: +0,16; bỏ nhìn trước EPS còn −0,77.',
                'doc': 'Alpha vẫn lẫn nhịp thị trường (luật hay bật khi cả thị trường đang giảm rồi hồi), nên cần thêm “vượt cùng ngày”.'},
               {'nhom': 'Đo kết quả',
                'term': 'Vượt cùng ngày',
                'nghia': 'Lợi suất 60 phiên của mã trừ lợi suất 60 phiên trung bình của mọi mã mua cùng ngày. Gỡ phần cả thị trường cùng lên cùng '
                         'xuống, chỉ giữ phần mã tự làm được.',
                'vi_du': 'Gộp gần 400 mã, ngày bật: +1,13 điểm %; trễ EPS 45 ngày còn +0,22. HPG theo 47 mốc độc lập: +2,83 điểm %, p 0,23.',
                'doc': 'Đây là thước đo “luật có chọn được mã tốt hơn mặt bằng không”; gần 0 là luật chỉ đi theo nhịp chung.'},
               {'nhom': 'Đo kết quả',
                'term': 'Vượt lãi tiền gửi',
                'nghia': 'Một lần mua “thắng tiền gửi” khi lợi suất 60 phiên lớn hơn LS của chính ngày mua × 60 ÷ 250, tức lãi tiết kiệm cộng dồn '
                         'cùng kỳ theo lãi suất của ngày đó.',
                'vi_du': 'Với LS hôm nay 7,60% rào là khoảng 1,82%; ví dụ ở năm LS 12% rào là 2,88%. Tính trên toàn lịch sử, mỗi ngày dùng LS của '
                         'ngày đó: HPG 43,4% số ngày bật vượt rào; gộp gần 400 mã 47,1%.',
                'doc': 'Trả lời đúng câu hỏi gốc của TV (có hơn gửi tiết kiệm không) tốt hơn Hit.'},
               {'nhom': 'Kiểm định',
                'term': 'Mốc độc lập (trang còn gọi là khối hoặc đợt độc lập)',
                'nghia': 'Ba tên, cùng một nghĩa. Lấy ngày bật đầu tiên làm mốc, mốc kế tiếp phải cách ít nhất 60 phiên, để cửa sổ đo không chồng '
                         'nhau. Hai ngày liền nhau dùng chung 59/60 phiên nên đếm theo ngày là đếm một trải nghiệm nhiều lần.',
                'vi_du': 'HPG: 1.748 ngày bật nhưng chỉ 47 mốc. VN-Index vùng ERP +2 đến +5: 1.629 ngày, 48 khối.',
                'doc': 'Độ chắc của một tỷ lệ đi theo số mốc, không theo số ngày.'},
               {'nhom': 'Kiểm định',
                'term': 'Nhìn trước EPS và bản trễ 45 ngày',
                'nghia': 'Bloomberg ghi EPS quý mới vào đúng ngày cuối quý, trong khi BCTC ra sau 3 đến 7 tuần, nên backtest “biết” lợi nhuận trước '
                         'thị trường. Bản trễ 45 ngày xấp xỉ việc chỉ dùng lợi nhuận đã công bố: ở ngày t, P/E tính bằng EPS của 45 ngày trước (hạn '
                         'BCTC hợp nhất quý), rồi tính lại percentile và tín hiệu. Đây là quy ước chung, không phải ngày công bố thật của từng mã.',
                'vi_du': 'Gộp gần 400 mã: vượt cùng ngày +1,13 → +0,22 điểm %; Hit khi bật 52,0% → 50,6% (ngày bất kỳ 51,8%). HPG: Hit 48,3% → '
                         '45,4%.',
                'doc': 'Số ghi “trễ EPS 45 ngày” hay “không nhìn trước EPS” sát thực tế giao dịch hơn; hai bản lệch xa thì phần chênh là lợi thế '
                       'ảo.'},
               {'nhom': 'Kiểm định',
                'term': 'Hướng LS 6 tháng',
                'nghia': 'LS hôm nay trừ LS 182 ngày trước, chia 5 ô: dưới −0,5 giảm mạnh; −0,5 đến dưới −0,1 giảm; −0,1 đến +0,1 đi ngang; trên '
                         '+0,1 đến +0,5 tăng; trên +0,5 tăng mạnh. Công thức TV không dùng biến này.',
                'vi_du': 'Hiện +0,6 (7,0% lên 7,60%) → tăng mạnh. LS giảm: ngày bật TB +7,25%, Hit 59,4%; mọi ngày +6,13%, Hit 58,7%. LS tăng mạnh: '
                         'ngày bật −0,80%, Hit 41,8%; mọi ngày +0,02%, Hit 43,6%.',
                'doc': 'Về lợi suất tuyệt đối, cột “luật bật” và “mọi ngày” đi cùng thứ tự, nên phần lớn chênh lệch là của nhịp lãi suất chứ không '
                       'phải của luật. Mỗi ô chỉ gồm khoảng 10 giai đoạn lãi suất từ 2008.'},
               {'nhom': 'Kiểm định',
                'term': 'Tỷ lệ đã hiệu chỉnh về rổ (cột “Co”)',
                'nghia': 'Mã chỉ có vài mốc cho mỗi điều kiện nên tỷ lệ thô dễ ăn may. Co = (k + 8 × p_rổ) ÷ (n + 8), với k mốc thắng, n mốc, p_rổ '
                         'là tần suất của VN100 cùng điều kiện; giống cộng thêm 8 mốc “ảo” mang tỷ lệ của rổ. Khác hẳn chữ “co P/E” ở pha giá (P/E '
                         'thu hẹp).',
                'vi_du': 'HPG, luật bật VÀ LS tăng mạnh, không nhìn trước EPS: 2/9 = 22,2%; rổ 44,3%; co = (2 + 8 × 0,443) ÷ 17 ≈ 32,6%. Hàng “Mọi '
                         'thời điểm”: thô 56,0%, co 55,7%.',
                'doc': 'Mốc càng ít thì co càng gần tỷ lệ rổ; đọc cột Co trước cột thô và so co với co. Vẫn là tần suất lịch sử, không phải xác suất '
                       'dự báo.'},
               {'nhom': 'Kiểm định',
                'term': 'KTC 90%, p và độ chắc t',
                'nghia': 'KTC 90% (khoảng tin cậy 90%) là dải ước lượng quanh tỷ lệ thắng; mẫu càng ít mốc thì dải càng rộng. p là khả năng ra kết '
                         'quả lệch cỡ đó chỉ do may nếu luật thật ra vô dụng; dưới 0,05 mới coi là khó do may. Độ chắc t cùng ý: dưới khoảng 2 thì '
                         'coi như chưa phân biệt được với may rủi.',
                'vi_du': 'HPG 2/9 mốc: dải 7,6% đến 49,6%, tức dữ liệu chưa đủ để nói chắc hơn. HPG vượt cùng ngày +2,83, p 0,23.',
                'doc': 'Dải còn chứa tỷ lệ của “Mọi thời điểm” (với HPG khoảng 56%) thì chưa nói được luật hơn mua bất kỳ lúc nào. Quét nhiều mã thì '
                       'luôn có vài mã “đẹp” do may.'},
               {'nhom': 'Kiểm định',
                'term': 'Thiên lệch sống sót',
                'nghia': 'Bộ 405 mã là thành viên VN-Index hiện tại; mã từng “rẻ” rồi huỷ niêm yết không có trong dữ liệu, mà đó đúng là loại mã '
                         'luật sẽ mua.',
                'vi_du': 'VN30 và VN100 không có chỉ số lịch sử thật nên trang dựng từ thành viên hiện tại.',
                'doc': 'Mọi kết quả backtest ở đây nghiêng về phía đẹp hơn thực tế.'},
               {'nhom': 'Định giá HHP & bằng chứng',
                'term': 'σ HHP',
                'nghia': 'HHP là phương pháp định giá theo dải bội số của Huỳnh Hoàng Phương: so P/E (hoặc P/B với ngân hàng, bất động sản, dịch vụ '
                         'tài chính, bảo hiểm, tài nguyên cơ bản, hoá chất, dầu khí) hôm nay với mức của chính mã từ 12/2017. μ (đọc là “mu”) là mức '
                         'trung bình; σ (sigma) là biên dao động thường gặp quanh mức đó. Thường khoảng 2/3 thời gian bội số nằm trong μ ± 1σ, nên '
                         'dưới −1σ là vùng rẻ ít gặp, trên +1σ là đắt.',
                'vi_du': 'HPG thuộc ngành Tài nguyên Cơ bản (thép xếp vào đây) nên dùng P/B: hôm nay 1,23, trung bình 1,78, biên dao động 0,50; thấp '
                         'hơn trung bình 0,55, bằng 1,10 lần biên → −1,10σ, vùng rẻ. Đổi ra giá: −2σ 12.932đ, −1σ 21.319đ, μ 29.706đ.',
                'doc': 'HHP hỏi rẻ so với chu kỳ khoảng 8 năm, TV hỏi rẻ so với 1 năm; cả hai cùng rẻ thì chắc hơn. Khi dải −2σ đổi ra giá gần 0đ '
                       '(bội số dao động quá mạnh) thì trang không chấm phía rẻ.'},
               {'nhom': 'Định giá HHP & bằng chứng',
                'term': 'Pha giá (EPS × P/E)',
                'nghia': 'Giá chia thành các pha, mỗi pha kết thúc khi giá tuần đảo chiều từ 25% trở lên; vì giá = EPS × P/E, mỗi pha tách được phần '
                         'do lợi nhuận và phần do thị trường trả bội số khác.',
                'vi_du': 'HPG từ 12/09/2025: giá −23,5% trong khi EPS +72,8% và P/E từ 16,8 xuống 7,5 lần, lúc LS đi từ 6,1% lên 7,6%: giảm vì P/E '
                         'thu hẹp (nhãn trên trang: “co P/E”).',
                'doc': 'P/E thấp của HPG hiện nay đến từ lợi nhuận tăng mà thị trường không trả thêm, không phải lợi nhuận sụt.'},
               {'nhom': 'Định giá HHP & bằng chứng',
                'term': 'Mức hội tụ bằng chứng',
                'nghia': 'Sáu chiều chấm +1, 0 hoặc −1: TV, σ HHP, ERP (+1 từ +5, −1 khi âm), Lịch sử (chỉ khi p < 0,1), EPS FY2026 đồng thuận '
                         '(trung bình dự báo của các công ty chứng khoán; +1 từ +15%), Chủ thể (người nội bộ và cổ đông lớn mua/bán ròng từ 0,1% số '
                         'cổ phiếu trong 12 tháng). Tổng từ 3 là Hội tụ mạnh, 2 Hội tụ, 0–1 Lẫn lộn, âm Ngược chiều.',
                'vi_du': 'HPG 5 điểm: TV +1, HHP +1, ERP +1, Lịch sử 0 (p 0,23), EPS +1 (+64%), Chủ thể +1 (+0,39%). Cùng lúc “Thắng 60 (co)” chỉ '
                         '32,6%.',
                'doc': 'Đếm xem các nguồn có cùng chiều không, không phải xác suất lên giá hay lệnh mua/bán. Chiều TV +1 chỉ ghi nhận mã đang rẻ so '
                       'với chính nó; kiểm định cho thấy riêng điều này không đem lại lợi thế, nên đừng cộng dồn điểm thành độ chắc chắn. Hướng LS '
                       'không nằm trong sáu chiều nên luôn đọc kèm Thắng 60 (co) và điểm gãy.'},
               {'nhom': 'Định giá HHP & bằng chứng',
                'term': 'Bậc bằng chứng (FACT / SS-T3 / EST)',
                'nghia': 'Nhãn cho biết con số đến từ đâu: FACT-T1 số gốc chính thức; FACT-T2 nhà cung cấp dữ liệu (Bloomberg, FiinProX, Vietcap '
                         'IQ); SS-T3 bên thứ ba (Toàn Vũ, công ty chứng khoán, EPS đồng thuận); EST phép tính của Hội đồng.',
                'vi_du': 'HPG: giá, P/E, LS là FACT-T2; EPS FY2026 +64% là SS-T3; percentile 2,8, ERP +5,81, co 32,6% là EST.',
                'doc': 'Hai số mâu thuẫn thì tin bậc cao hơn; UNVERIFIED không dùng cho quyết định.'}],
 'kiem_dinh': [{'tieu_de': 'Luật tái lập được; lệch lớn nhất nằm ở con số lãi suất',
                'text': 'Phần này là nhận xét của Hội đồng (nhóm phân tích dựng trang, độc lập với TV), không phải của TV. Chạy lại luật bằng chính '
                        'dữ liệu TV gửi, percentile khớp tuyệt đối. Thứ tự xếp hạng alpha của 53 mã TV in gần như trùng bản chạy lại (độ khớp thứ '
                        'hạng 0,91, tối đa là 1), nhưng chỉ 58% số mã lệch trong 2 điểm, và vài mã lệch lớn chưa rõ nguyên nhân (DAT, PTL, SVT). '
                        'Lệch lớn nhất ở đầu vào: LS “hiện tại” 11,78% là dòng 03/03/2008, dòng cũ nhất của tệp FiinProX; LS đúng là 7,60% nên '
                        'ngưỡng đúng là 29,6 chứ không phải 13. Các percentile “hiện tại” trong báo cáo là của phiên 07/09/2026, không phải 06/10.'},
               {'tieu_de': '“Thị trường rẻ” tuỳ vào việc bỏ mã nào',
                'text': 'P/E thị trường 9,5 lần của TV là P/E gộp sau khi bỏ các mã P/E trên 40, dù báo cáo ghi “cap-weighted”; phép bỏ này loại 30 '
                        'mã chiếm 26,0% vốn hoá, chủ yếu VIC. Phiên 05/10/2026: cách TV 9,16 lần, ERP +3,32 (tích lũy); đủ mã 11,88 lần, ERP +0,82 '
                        '(hòa); ngoài họ Vin 9,77 lần, ERP +2,64. Cùng một thị trường, đổi cách đo là đổi vùng.'},
               {'tieu_de': 'Bỏ “biết trước lợi nhuận” thì luật hết lợi thế',
                'text': 'Chuỗi P/E lịch sử của Bloomberg dùng lợi nhuận quý từ ngày cuối quý, trước khi BCTC ra 3 đến 7 tuần. Chỉ dùng lợi nhuận đã '
                        'công bố (xấp xỉ bằng trễ 45 ngày) thì ngày luật bật có Hit 50,6%, thấp hơn cả ngày bất kỳ (51,8%); phần vượt mọi mã cùng '
                        'ngày từ +1,13 còn +0,22 điểm % (tính theo trung bình từng ngày: +1,11 còn +0,13; độ chắc t từ 4,0 còn 0,5, cần khoảng 2 trở '
                        'lên mới đáng kể); alpha kiểu TV từ +0,16 thành −0,77.'},
               {'tieu_de': 'Đếm đúng thì số mã “hợp luật” gần bằng số mã do may',
                'text': 'Xếp hạng của TV đếm mọi ngày tín hiệu, trong khi các ngày liền nhau gần như trùng kết quả. Đếm lại bằng mốc cách nhau ít '
                        'nhất 60 phiên và so với mọi mã cùng ngày: 12/380 mã vượt trội có ý nghĩa (p < 0,05). Nếu luật hoàn toàn vô dụng, cứ 100 mã '
                        'vẫn có khoảng 2,5 mã trông “vượt trội có ý nghĩa” chỉ nhờ may: 380 × 2,5% ≈ 9,5 mã; khả năng may rủi tự cho ra từ 12 mã trở '
                        'lên là khoảng 25%. Bảng xếp hạng vì thế giống danh sách mã hưởng lợi từ các nhịp hồi chung hơn là mã có tín hiệu hiệu quả.'},
               {'tieu_de': 'Hướng đi của lãi suất chi phối lợi suất tuyệt đối',
                'text': 'Tách theo hướng LS 6 tháng. LS giảm: ngày luật bật trung bình +7,25% sau 60 phiên, Hit 59,4%; mọi ngày +6,13%, Hit 58,7%. '
                        'LS tăng mạnh: ngày luật bật −0,80%, Hit 41,8%; mọi ngày +0,02%, Hit 43,6%. Trong từng hướng hai bên gần bằng nhau: lời hay '
                        'lỗ chủ yếu do LS đang lên hay xuống, không phải do luật; riêng phần vượt mọi mã cùng ngày (bản còn nhìn trước EPS) thì khác '
                        'theo hướng, +2,86 điểm % khi LS giảm và +0,26 khi tăng mạnh. Mỗi hướng chỉ gồm khoảng 10 giai đoạn lãi suất từ 2008, nên '
                        'đây là quan sát trên ít chu kỳ, chưa phải quy luật. Ngưỡng siết theo MỨC LS cũng không thêm gì: ngưỡng cố định P27,6, chọn '
                        'để có độ phủ tương đương (khoảng một phần ba số mã bật mỗi ngày), cho vượt cùng ngày +1,27, nhỉnh hơn ngưỡng động (+1,13). '
                        'Hiện LS +0,6 điểm trong 6 tháng, ô “tăng mạnh”.'},
               {'tieu_de': 'Thứ còn đứng: ERP của chính từng mã',
                'text': 'Sau khi bỏ biết trước lợi nhuận, trong các biến đã kiểm (ngưỡng, hướng LS, vùng 52 tuần, ERP), ERP từng mã (100 ÷ P/E − LS) '
                        'là biến còn tách được nhóm mã tốt khỏi nhóm kém: nhóm ERP trên 10 hơn mặt bằng cùng ngày +1,06 điểm %, nhóm dưới −3 kém '
                        '1,80 điểm % (Hit 44,3%); hiệu ứng của nhóm cao nhất nhỏ đi khoảng 1/3 so với bản còn nhìn trước EPS. Đây đúng là khái niệm '
                        'TV dùng khi nói chuyện nhưng không có trong code backtest của TV. Lưu ý chung: bộ 405 mã là thành viên VN-Index hiện tại, '
                        'mã rẻ rồi huỷ niêm yết không có mặt, nên mọi kết quả lịch sử có thể đẹp hơn thực tế.'}],
 'doc_bieu_do': {'vitri': 'Ba ô đầu đúng phép tính TV: P/E rổ (bỏ mã P/E trên 40), P/E hòa tiền gửi (TV gọi là P/E fair) = 100 ÷ LS và mức rẻ hơn '
                          'mức hòa; ô ERP cho biết cổ phiếu đang trả thêm bao nhiêu điểm % so với gửi tiết kiệm. So ERP cách TV với ô “đủ mã” và '
                          '“ngoài họ Vin”: rơi vào hai vùng khác nhau thì kết luận “rẻ” phụ thuộc cách đo. Ô hướng LS màu đỏ nghĩa là LS 6 tháng '
                          'đang đi lên.',
                 'chart2': 'Ba panel đọc từ trên xuống ở cùng một mốc thời gian. Panel 1: đường lam (P/E rổ) nằm dưới đường cam đứt (P/E hòa tiền '
                           'gửi) là vùng xanh, cổ phiếu cho lợi suất lợi nhuận cao hơn tiền gửi; nằm trên là vùng đỏ. Panel 2 là LS (trên 10% là '
                           'vùng nguy hiểm theo TV), panel 3 là ERP với các vạch +5, +2, 0, −3 của TV; dải nền là 7 giai đoạn TV đặt tên.',
                 'erpzone': 'Mỗi cột là một vùng ERP; chiều cao là tỷ lệ những ngày VN-Index 60 hoặc 120 phiên sau cao hơn nếu mua lúc ERP ở vùng đó '
                            '(vạch 50% là tung đồng xu). Chiều cao cột tính theo NGÀY; số khối độc lập ở nhãn phụ cho biết con số đó chắc tới đâu: '
                            'vùng +2 đến +5 có 1.629 ngày, Hit 58,3%, nhưng chỉ gom được 48 khối không chồng nhau, nên độ chắc chỉ ngang khoảng 48 '
                            'lần quan sát.',
                 'chart1': 'Trục ngang là P/E lúc mua, trục dọc là lợi suất trung bình (hình trên) hoặc Hit, tức tỷ lệ lần giá cao hơn (hình dưới), '
                           'sau 60/120 phiên. So đường cách TV với đường “trễ EPS 45 ngày”: khoảng hở giữa hai đường là phần lợi thế đến từ việc '
                           'biết trước lợi nhuận quý. Hình thứ ba (P/E cả rổ) dùng P/E cả rổ và lợi suất chỉ số, đúng câu hỏi TV đặt ra.',
                 'rank': 'Hai hình trên là xếp hạng alpha kiểu TV (mọi ngày tín hiệu, cửa sổ chồng nhau). Hai hình dưới xếp lại chính các mã đó theo '
                         'mốc độc lập và so với mọi mã cùng ngày; chỉ cột đậm (p < 0,05) là khó do may, và nhớ khoảng 2,5% số mã đạt màu đó dù luật '
                         'vô dụng.',
                 'watch': 'Ba hình cho danh mục tham chiếu và watchlist TV: Hit (tỷ lệ lần giá 60 phiên sau cao hơn) khi luật bật, xanh trên 55%, đỏ '
                          'dưới 50%; lợi suất TB khi bật so với mọi ngày; và alpha cách TV đặt cạnh bản trễ EPS 45 ngày (cột xám). Mã đẹp ở cột màu '
                          'mà xấu ở cột xám là đang đẹp nhờ nhìn trước lợi nhuận.',
                 'regime': 'Hình trái chia kết quả theo MỨC LS lúc luật bật (cách TV), hình giữa chia theo HƯỚNG LS 6 tháng; LS hiện ở ô “tăng mạnh” '
                           'nên đọc hình giữa trước, và cột màu (luật bật) gần bằng cột xám (mọi ngày cùng hướng) nghĩa là kết quả đến từ nhịp lãi '
                           'suất, không từ luật. Nhãn kiểu “LS 8–10% · hit 68,5%” đọc là: trong những ngày luật bật lúc lãi tiền gửi ở khoảng 8–10%, '
                           'có 68,5% số ngày giá 60 phiên sau cao hơn; LS là điều kiện, hit là kết quả, và tỷ lệ này đếm theo ngày nên các ngày liền '
                           'nhau bị đếm trùng. Hình phải: mỗi chấm một mã, góc phải trên là Hit trên 50% và alpha dương.',
                 'signals': 'Cột là percentile P/E hiện tại của từng mã: thấp hơn vạch vàng (ngưỡng đúng P29,6) là luật đang bật; vạch đỏ P13 là '
                            'ngưỡng TV in do đọc nhầm LS. Hình dưới xếp các mã đang bật theo Hit lịch sử kiểu TV (đếm từng ngày, EPS nhìn trước), '
                            'nhãn phụ là percentile và ERP. Đây là bộ lọc thô, không phải danh sách mua.',
                 'hhp': 'Ô số và hai đường P/E, P/B của rổ đặt trong dải μ ± σ của chính rổ từ 12/2017 (HHP: phương pháp dải bội số của Huỳnh Hoàng '
                        'Phương): dưới −1σ là rẻ so với chu kỳ, trên +1σ là đắt. Đọc P/E và P/B cùng lúc theo quy tắc ở cuối mục này: rẻ cả hai là '
                        'đáng tin nhất, P/E rẻ mà P/B đắt là dấu hiệu lợi nhuận đang ở đỉnh.',
                 'vimo': 'Các ô và đường đặt cạnh nhau những thước đo lãi suất khác nhau; luật TV chỉ dùng một trong số đó (FiinProX trên 12 tháng '
                         'cao nhất, số tháng). Khi lãi niêm yết ngân hàng lớn đứng yên mà liên ngân hàng, TPCP đi lên, con số LS của TV có thể chưa '
                         'phản ánh giá vốn thật. Bảng điều kiện đáy chu kỳ (theo khung vĩ mô của SGI Capital, phương pháp Lê Chí Phúc) cho biết chu '
                         'kỳ tiền đã đổi chiều chưa.',
                 'bangchung': 'Mỗi hàng một mã, sáu chiều chấm +1 (xanh, ủng hộ), 0 hoặc −1 (đỏ, ngược); “Điểm” là tổng, “Mức hội tụ” là nhãn, và '
                              'chiều TV +1 chỉ nói mã đang rẻ so với chính nó, không nói luật đã được chứng minh. Rê chuột lên ô để xem lý do, và '
                              'luôn đọc kèm “Thắng 60 (co)”: Hit 60 phiên đếm theo mốc độc lập khi luật bật đúng chiều LS hiện tại, không nhìn trước '
                              'EPS, đã hiệu chỉnh về rổ; cùng cột “Gãy”. Đây là mức hội tụ bằng chứng, không phải khuyến nghị.',
                 'pha': 'Giá chia thành các pha, mỗi pha kết thúc khi giá đảo chiều từ 25% trở lên; vì giá = EPS × P/E, mỗi pha tách phần do lợi '
                        'nhuận và phần do bội số. Xanh là tăng nhờ lợi nhuận, lam tăng nhờ P/E, vàng giảm vì P/E thu hẹp (nhãn trên trang ghi “co '
                        'P/E”, khác hẳn cột “Co” ở bảng xác suất), đỏ giảm do lợi nhuận. Rê chuột lên mốc cuối pha để xem LS, VN-Index và giao dịch '
                        'nội bộ trong pha.',
                 'hhpma': 'Đường giá đi trong dải σ của chính mã đã đổi ra giá: dải ±1σ, ±2σ, đường cam μ là giá theo bội số trung bình, đoạn chấm '
                          'sau hiện tại là dự phóng 36 tháng, kim cương là giá mục tiêu bên thứ ba. Giá dưới dải −1σ là rẻ so với chu kỳ của mã. '
                          'Bảng “Vùng σ lúc mua” cũng dùng dữ liệu tương lai, nhưng khác lỗi EPS: μ và σ tính trên cả giai đoạn tới nay, nên một '
                          'ngày mua năm 2018 đã “biết” mức trung bình của các năm 2019 đến 2026.',
                 'xacsuat': 'Mỗi hàng là một điều kiện (mọi lúc, luật bật, hướng LS, vùng ERP, mỗi cái có bản không nhìn trước EPS); “Mốc” là số lần '
                            'vào không chồng nhau, “Thắng 60” chính là Hit 60 phiên nhưng đếm trên mốc độc lập thay vì từng ngày như cách TV, “Co” '
                            'là tỷ lệ đã hiệu chỉnh về tần suất VN100 cùng điều kiện. Đọc cột Co cùng KTC 90% (khoảng tin cậy), và so Co của hàng '
                            '“Luật TV bật VÀ LS cùng hướng hiện tại · không nhìn trước EPS” với Co của hàng “Mọi thời điểm”.',
                 'chuthe': 'Bảng giao dịch của người nội bộ và cổ đông lớn đã thực hiện, đang đăng ký, cùng các sự kiện vốn (cổ tức, phát hành) của '
                           'mã. Lệnh mua trùng đợt quyền mua hoặc ESOP được tách riêng, không tính vào mua ròng trên sàn; giao dịch mới đăng ký thì '
                           'chưa chắc đã thực hiện.'}}
