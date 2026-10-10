#!/usr/bin/env python3
"""
Fincept Terminal — Lăng kính cấu trúc cổ đông & FFT: CHỮ CỐ ĐỊNH (nguyên văn phương pháp / hợp đồng).
Tách khỏi phần dựng trang (≤800 dòng/tệp). Không sửa chữ ở đây khi chưa đối chiếu lại nguồn ghi cạnh từng hằng.
Khối §1, 11 câu bắt buộc: chép từ u3.md mục H/G. PILLAR3_MD, NTH_MD: trích bằng máy từ tệp skill (xem nguồn).
"""

# §1 NGUYÊN VĂN từ u3.md mục H (khối cố định của lang_kinh_fft_daily.html) — không sửa chữ.
PP_TEXT = """\
1 · Phương pháp luận FFT — Toàn Vũ
Khối cố định trong mọi bản báo cáo · nguồn: chat Toàn Vũ 20/08 & 04/09/2026 + Methodology v1.7

1 · Định nghĩa & vì sao
FFT = KL khớp lệnh trong kỳ ÷ Free float × 100 (%)
Bản báo cáo này tính FFT theo ngày rồi lấy trung bình các ngày trong tuần, và làm mượt tiếp 4 tuần (cột "FFT 4w").
"Cái này sẽ loại đi hết các yếu tố tăng giá, chia cổ tức v.v. — lúc đấy sẽ thấy luôn được khi nào thì cp bước vào trạng thái gd trầm lắng thật." — Toàn Vũ, 04/09/2026.
Khối lượng tuyệt đối vô nghĩa khi so giữa các mã và bị méo bởi chia thưởng. Chia cho free float biến nó thành tỷ lệ phần trăm số cổ phiếu tự do thực sự đổi tay — so được theo thời gian và giữa các mã.

2 · Ngưỡng riêng từng mã
Không có ngưỡng chung. Mỗi mã dùng phân phối lịch sử của chính nó:
P10 = vùng cạn cung — thanh khoản đáy 10% lịch sử. P90 = vùng phân phối — đỉnh 10%.
Cột ×P10 = FFT hiện tại gấp bao nhiêu lần ngưỡng cạn cung 3 năm. Cột pct = vị trí trong 156 tuần gần nhất (0 = cạn nhất, 100 = sôi động nhất).
Một mã có FFT 0,2% có thể là "đang sôi" (LPB) trong khi mã khác 1,5% vẫn là "bình thường" (VIX) — luôn đọc theo ngưỡng của chính mã.

3 · Chu trình 3 pha
Gom hàng — FFT cao/spike liên tục nhưng giá đi ngang. Có người mua lượng lớn mà giá không lên: hàng đang chuyển tay. (STB 2022–24, vùng 20–33K.)
Lock / bo cung — FFT sập về P10, giá bắt đầu tăng. "Markup không vol": float còn lại quá mỏng nên giá lên nhẹ nhàng. (STB 2025–26: FFT 1,4% → 0,22% khi giá 33 → 77K.)
Phân phối — FFT bật lên P90 khi giá giảm. Hàng được đẩy ra cho retail đỡ. (FPT Q1/2026: FFT đỉnh 1,2% khi giá 99 → 65K.)

4 · Bo cung qua margin — vì sao chủ DN phải kéo
Margin toàn thị trường 42 → 445 nghìn tỷ (×8,1) trong khi vốn hoá chỉ ×2,5; margin tách rời GTGD/phiên từ 2022 và gần như không reset ⇒ phần tăng thêm không phải tiền trade mà là margin để hold: chủ DN cắm cổ phiếu vay tiền khi bank chạm LDR/room.
Hệ quả: cổ đã cắm bị cô đặc tự nhiên (không được bán) và chủ DN buộc phải giữ định giá ≥ mức đã rút margin. Phản trực giác: ông vay khoẻ nhất mới là ông cổ tăng nhất; MWG/HPG tiền nhiều, không cần vay — không ai có nghĩa vụ kéo.
Mặt trái: Margin/Mcap 5,4% là ATH. Khi có shock, chính nhóm cắm nhiều nhất bị giải chấp trước, và cổ bo cung rơi nhanh nhất vì float đã cạn, không có người mua tự nhiên.

5 · Market FFT → chọn bucket
Cộng toàn thị trường: vùng phân phối ≈1,30%, vùng cạn cung ≈0,35%.
Market FFT thấp/giảm (như hiện nay) → tiền đầu cơ không hoạt động → chỉ cổ bo cung có chủ DN trợ lực mới đi được.
Market FFT bật từ đáy + regime GREEN → chuyển sang beta cao: chứng khoán, BĐS, midcap định giá rẻ.
Đầu 2026 index tăng nhưng Market FFT giảm diện rộng — chính chart này trả lời câu "có tách VIN ra không".

6 · Sau khi gom xong: biên độ ±10%/quý
10,8%/năm (margin thực) + ~1,2% nuôi team ≈ 12%/năm ≈ 3%/quý
Team trading chỉ ăn ~30% biên độ nhịp ⇒ nhịp cần ≈ 10%/quý
Với mã đã lock (STB, VIC, VHM), giao dịch còn lại chỉ là trading giữ giá để nuôi chi phí margin: chu kỳ ~3 tháng, biên ±10%, TT xấu −12–15% từ đỉnh.
Các phiên vol lớn ở vùng giá tăng = họ đang bán. Không đua.

[Ma trận]  cột: Giá ↑ | Giá ↓ / đi ngang
FFT ↑ · Markup có retail — Đầu sóng thì tốt; nếu FFT > P90 và Δ cổ đông tăng ⇒ Pattern A (đỉnh). Không mua đuổi.
FFT ↑ · Phân phối / đổi chủ — Hàng được đẩy ra khi giá giảm. Phân biệt "tháo hàng" với "đổi chủ" bằng Pillar III + GUO.
FFT ↓ · Bo cung — markup không vol — Vùng lý tưởng: float đã lock, giá lên không cần thanh khoản. Kiểm tra chủ DN có động cơ giữ giá không.
FFT ↓ · Tích luỹ / cạn cung — Hoặc đang gom xong chờ markup, hoặc "mất hút thanh khoản" sau khi sập — phân biệt bằng ý đồ chủ thể.
FFT ↔ · Chưa có tín hiệu. | —

[Bắt buộc] FFT không dùng đơn lẻ
FFT là Pillar V — đo cung/cầu trên float. Một quyết định vào lệnh cần thêm: Δ cổ đông BCTN đã chỉnh corporate action (Pillar I), VWAP cụm 6/12/24M (Pillar II), câu hỏi vàng "mục đích kéo có lớn hơn chi phí kéo?" và "chủ DN đã cắm bao nhiêu margin, sàn bảo vệ ở đâu?" (Pillar III), dòng tiền 4 kênh FiinTrade (Pillar IV). Cuối cùng phải qua Kill zone (Munger · Klarman · VN Political Risk) và Kelly sizing. Vị thế 2–12% NAV, stop 15–20%.
"""
PP_NGUON = ("Nguồn: khối §1 nguyên văn từ lang_kinh_fft_daily.html dòng 110–156 (lang_kinh_fft_vn30.html dòng "
            "128–174 giống hệt) — Cowork outputs; chép qua đặc tả u3.md mục H, không sửa chữ. Chip mã trong ma trận "
            "gốc là dữ liệu nên đã bỏ — xem view Ma trận.")
PP_CONG_THUC = {1: (1,), 6: (1, 2)}  # dòng công thức của thẻ 1 và thẻ 6
MX_TIEU_DE = ("Markup có retail", "Phân phối / đổi chủ", "Bo cung — markup không vol", "Tích luỹ / cạn cung")
SAO_LECH = [
    "★1 Thẻ 1 nói FFT \"so được… giữa các mã\" — v1.7 [M]:330 cấm so FFT tuyệt đối giữa các mã; chỉ so "
    "percentile trong cùng một mã.",
    "★2 Thẻ 5 dùng neo tuyệt đối ≈0,35% / ≈1,30% — v1.7 [M]:175–180 thay bằng P10 / P90 của chính rổ.",
    "★3 Ghi chú \"FFT không dùng đơn lẻ\" dẫn \"dòng tiền 4 kênh FiinTrade\" — SKILL [S]:199 ghi 2/4 kênh và không "
    "dùng FiinTrade.",
    "★4 Thẻ 4 và 6 nêu 5,4% không kèm nhãn SS-T3 — DATA_SOURCES [DS]:166 bắt buộc kèm nguồn Toàn Vũ + SS-T3 + câu "
    "\"chưa tái lập độc lập\".",
]


# 11 câu bắt buộc NGUYÊN VĂN (DATA_SOURCES cột 3, qua u3.md mục G) — thiếu câu = báo cáo không hợp lệ.
CAU_BAT_BUOC = [
    "Vế 2 của A, B, C và vế cuối của D `[CẦN DATA]`. Mã ngoài lưới 100 mã W37 **không phân loại được**.",
    "Ngưỡng 0,35 / 1,30% dùng bằng **P10 / P90 của chính rổ**. Mọi FFT tuyệt đối của 85 mã ghi kèm `EST (hệ số 1,075, n=13)`.",
    "CF đọc là **'chưa có số mới'**, không phải 'không đổi'. Cấm tính Δ cổ đông kỳ cuối, cấm tính k, cấm gán Pattern B/D cho mã có CF ở mốc cuối.",
    "Mọi phát biểu Pillar I ngoài 30 mã ghi `proxy — chưa có Δ cổ đông thật`. Mọi tỷ lệ giữ mẫu số gốc `x/30`, **không viết thành `x/100`**.",
    "Mức thị trường thay bằng **−(NN + tự doanh)**; mức mã thay bằng **Δ cổ đông Khối 7**. Không gán A/B dựa riêng dòng khối ngoại.",
    "Cơ sở KL toàn báo cáo là **khớp lệnh thuần**. **Cấm suy KL thoả thuận từ chênh lệch tổng KL.** Mã nghi D ghi `chưa kiểm được`.",
    "Mọi mốc giá lịch sử là **giá danh nghĩa, chưa khử lạm phát/tỷ giá**.",
    "Ô pattern để **'—'**, không suy thành 'trung tính'. 36 mã này **không đủ điều kiện** vào bảng ứng viên thay thế.",
    "KSV giữ nhãn **UNVERIFIED**, không dùng cho quyết định.",
    "Trích 5,4% kèm nguồn Toàn Vũ + **SS-T3** + câu 'chưa tái lập độc lập'.",
    "Không trích rating / giá mục tiêu nào từ WiData kỳ này.",
]
LICH = ("Bridge: fft_langkinh 30′ ban ngày / 240′ ban đêm (gồm lớp chủ thể fft_chuthe.py — chỉ đọc KHO free_float, "
        "vietcap_fundamentals.json, owner_intent.json), fft_codong 720′ / 1440′ (goi_nguon LICH, sau các job vn_*). "
        "KHO: vn_lichsu — backfill sâu từ 2020 cho VN30 ∪ VN100, ≥18′ khi còn việc (ngoài 09:00–15:00), ngày thường "
        "≥21:00; vn_ff — free float VCI, ngày thường ≥21:40, ≥18′ khi còn mã thiếu (ngoài 09:00–15:00). App chỉ đọc "
        "tệp — không gọi mạng.")


# ── D6.2 · view chuthe — câu bắt buộc nguyên văn (nguồn ghi cạnh) + câu cố định của đặc tả ──
CHUTHE_BAT_BUOC = [
    ("S:179", "Mục đích lớn của chủ thể khi giữ/kéo giá là gì, và mục đích đó CÓ LỚN HƠN chi phí kéo không?"),
    ("M:849", "mỗi dòng cần CBTT hoặc nghị quyết gốc trước khi dùng cho quyết định"),
    ("R:184", "Chưa trả lời → không xếp hạng cơ hội · owner_intent chưa có CBTT gốc → SS-T3, chỉ định vị"),
    ("S:189", "'% khoá cao' và 'free float nhỏ' là hai cách nói cùng một con số … Cấm đếm nó hai lần."),
    ("M:950", "không suy thành 'trung tính'"),
    ("", "Nhãn là snapshot W37 10/09 — kỳ mới phải chấm lại (H17:111). Bằng chứng không đổi nhãn."),
]
CT_CAPTION = ("Bằng chứng chỉ để hiển thị — không đổi nhãn, không đổi playbook. NN/trần NN = sở hữu NN ÷ trần NN; "
              "không phải cột \"Room NN dùng\" của M:834-845 (không tái lập được). Khoá % = 100 − FF: cùng một con số "
              "với free float, không đếm hai lần.")
# D6.5 · câu cuối M:718 (nguyên văn, bỏ định dạng đậm)
M718 = "Trong kỳ tiền đắt, ô đáng tiền chỉ có giá trị khi chủ thể còn mục tiêu huy động (Khối 8)."
# R11 · note tĩnh tongquan
QUY_TAC_DOC = ("Vol bùng ở mã pct3Y cao + giá tăng = họ đang bán (trading-cost model); vol bùng ở mã pct3Y thấp + giá "
               "chưa chạy = cây breakout đầu tiên — Pattern C (Toàn Vũ · mũ sắt + chân cầu) chưa cài, chỉ ghi nhận.")
# R5 · note thitruong (không vẽ đường 0,35/1,30)
R5 = ("Ngưỡng tuyệt đối 0,35%/1,30% (Toàn Vũ) đã chuyển thành P10/P90 của chính rổ; neo 0,44% chỉ tái lập trên free "
      "float thấp (v1.7 Keynote 2).")
# R1 · bậc mức vs bậc hạng
MUC_EST = "Mức FFT = EST (free float VCI chưa đối chiếu legend v1.7) · thứ hạng/percentile = FACT-T2."
# R2, R4 · view nguon
R2 = ("Nguồn thứ hai hợp lệ cho free float chỉ là sổ cổ đông Vietcap IQ ×1,075 hoặc free-float factor HOSE; CẤM dùng "
      "Capital IQ Float% (khác định nghĩa: CapIQ/VCI MBB 1,98 · VPB 1,39 · HDB 1,06 · STB 1,05).")
R4 = ("Cơ sở KL: khớp lệnh thuần (VCI history). Đối chiếu cafef/SSI iBoard: [CẦN DATA] cho tới khi có một phiên 0 sai "
      "lệch. Không dùng Simplize.")
VCI_BAC = ("registry songuon_registry.json id vietcap-company ghi SS-T3 ⟷ M:905 #4 · M:912 #11 · S:125 ghi FACT-T2 — "
           "giữ FACT-T2, nêu mâu thuẫn (D1.1)")
# B5 · độ phủ Market FFT
PHU_THIEU = "độ phủ free float chưa đủ — percentile rổ chưa đại diện"
# D6.3 · note codong (câu đầu điền số đếm kiểu mốc từ fft_codong.json)
CD_KIEU = ("{ns}/{tong} mốc là công thức nội suy của tệp, {chep} mốc chép — vs đáy/đỉnh tính trên mốc quan sát; "
           "số W37 (gồm mốc nội suy) ở tooltip.")
CD_DAC_LAI = "Đặc lại: vs đáy ≤ +1% và vs đỉnh ≤ −5% (PT:182, EST)."
TV_HINH_THUC = ("Cột 'Hình thức tăng vốn' chỉ ghi 'Tăng vốn điều lệ lên …' — không tách thưởng/ESOP/cổ tức CP/phát "
                "hành thu tiền.")
# D6.7 · caption xephang
XH_CAPTION = "Đo lường, không phải xếp hạng cơ hội — Step 7 chưa trả lời cho {n}/{N} mã (R:184)."

# D6.9 · Pillar III — NGUYÊN VĂN ~/.claude/skills/langkinh-cautruc-codong/SKILL.md dòng 177–193 (trích bằng máy)
PILLAR3_NGUON = "~/.claude/skills/langkinh-cautruc-codong/SKILL.md dòng 177–193 (S:177-193)"
PILLAR3_MD = '### 3.3 Pillar III — Ý đồ chủ thể\n\n**Câu hỏi vàng:** *"Mục đích lớn của chủ thể khi giữ/kéo giá là gì, và mục đích đó CÓ LỚN HƠN chi phí kéo không?"*\n\nChạy **hai lần**: một lần ở Khối 0 (mức thị trường — đếm sự kiện vốn toàn rổ), một lần ở mức mã (chủ thể lớn nhất · % sở hữu · % khoá · room NN đã dùng · sự kiện tăng vốn 2025–26).\n\n**Keynote 10 — đảo một định kiến, và đây là phần quan trọng nhất của trụ này:**\n\n> Quan hệ **free float ⟷ percentile FFT trên 100 mã gần như bằng không**: có mã float 10% ở P70, có mã float 90% ở P3. **"Ít hàng trôi nổi" chỉ khuếch đại biên độ khi có người muốn kéo.** Trong kỳ tiền đắt, người muốn kéo là **người phải kéo: chủ thể đang có sự kiện vốn.**\n\n→ Hệ quả: **không được suy sóng từ free float nhỏ.** Phải suy từ nhu cầu vốn.\n\n📐 **Free float ở đây dùng đúng định nghĩa legend Khối 8 (xem §3.5):** phần còn lại sau khi trừ **Nhà nước · Chiến lược ≥5% · Nội bộ**, và **quỹ được tính là float**. Cột "% khoá" của bảng chủ thể chính là phần bị trừ ra — nên "% khoá cao" và "free float nhỏ" là **hai cách nói cùng một con số**, không phải hai bằng chứng độc lập. Cấm đếm nó hai lần.\n\nPhân tầng chủ thể (thứ tự đúng): **mục đích lớn hơn chi phí kéo** — VIC/VHM (HSR + VinFast), MSN (MSR), STB (VAMC), TCB (TCX). **Mục đích thuộc về Nhà nước, không thuộc về giá cổ phiếu** — GAS, PLX, BCM.\n\n⚠ Cột "mục đích lớn" lấy từ Hub `/sys/early_detection/owner_intent.json` (SS-T3): **mỗi dòng cần CBTT hoặc nghị quyết gốc trước khi dùng cho quyết định.**'
# D6.9 · NTH — NGUYÊN VĂN ~/.claude/skills/nguyen-tran-hai/SKILL.md dòng 45–46 (trích bằng máy)
NTH_NGUON = "~/.claude/skills/nguyen-tran-hai/SKILL.md dòng 45–46 (NTH:45-46)"
NTH_MD = '- **Cổ đông GIẢM ở vùng giá TĂNG/đỉnh = CÔ ĐẶC (BULLISH chất lượng):** vượt đỉnh không ai lỗ → người lãi chốt bớt → NĐT còn lại vững tâm lý, chất lượng tốt hơn. VD VIC/Vinhomes giảm **~hai-mươi-mấy-nghìn cổ đông** ở vùng đỉnh [V1@42:42]; Vincom giảm **~24.000 cổ đông** khi giá từ đáy 40→7x [V2@52:54].\n- **Cổ đông TĂNG VỌT ở đỉnh = PHÂN PHỐI cho retail (BEARISH):** tay-to xả cho NĐT mới vào.'
NTH_CHU_THICH = "tham chiếu SS-T3; chỉ ô CĐ↓×Giá↑ được mã hoá — EST"
NTH_7 = ("7 mẫu hình NTH chưa cài — hai bộ đánh số xung đột (NTH:55-61 ⟷ task Cowork "
         "`nguyentranhai-langkinh-daily/SKILL.md`:21-27).")
# R12 · Từ vựng — không trộn
TU_VUNG = [
    "Toàn Vũ A/B/C/D ≠ NTH P1–P7 (P1 \"Chân cầu\" của NTH ≠ C của Toàn Vũ; ngưỡng D: TV 2× nền 12 tuần, NTH >3× TB20).",
    "\"Intent\" của NTH ≠ \"chủ thể cần thị trường\".",
    "RED/YELLOW/GREEN (V2 Toàn Vũ) ≠ ĐẮT/RẺ (CỔNG) ≠ Regime Hub.",
    "\"ΔVol 2Y\" ≠ CBCI_V2 (công thức [CẦN DATA]).",
    "Module KHÔNG có CPVN/Hurst (BLOCKED), SM/CA (đình chỉ), SRVN (thiếu chuỗi 5 năm), Quality tiers cũ.",
]
# D6.8 · Nguồn đã xét & loại (danh sách tĩnh, mỗi mục một lý do)
NGUON_LOAI = [
    ("VN100_YDOCHUTHE_ALLINONE_live_data.json",
     "106/123 mã zero-fill thành BALANCED; source_pxts 02/05/2024; generated_at gắn nhầm hậu tố Z"),
    ("NGUYENTRANHAI_…REALTIME.html", "dừng từ 20/06; detect() dùng ngưỡng tự đặt"),
    ("Orchestrator/digest NTH", "plist không được nạp; 107 lần \"no signals\""),
    ("LangKinh_NTH_*.md", "văn xuôi LLM, ra tín hiệu BUY/SELL"),
    ("edi_index / mandate_registry / policy_map", "lớp nghị quyết, không phải nhu cầu vốn"),
    ("ownership_timeseries.json", "deltas: d30/d90_top5_pp null ở 123/123 mã; số insider từ 22/05"),
    ("simplize_vn100_ownership.json", "chỉ 17/123 mã có breakdown"),
    ("fund_intent_signals.json", "as_of 10/06; chưa qua gate LVF (M:923)"),
    ("owner_intent auto", "357 regex cap_raise_resolution; 300 ngày 31/12 giữ chỗ với date_approx=false; 51 ngày tương lai"),
    ("CHAEBOL_YDOCHUTHE_ALLINONE.html", "tĩnh từ 29/05, nhãn theo nhóm"),
]
