# Judge audit — replay CSV

Chạy replay bằng `python -m lab9.judge --csv <file> --audit 10`. Lớp dương tính là `FAIL`. Floor để dùng làm gate: κ ≥ 0.6, precision ≥ 0.8, recall ≥ 0.7.

## Calibration

| Tiêu chí | n | TP/FP/FN/TN | κ | Precision | Recall | Specificity | Fail rate quan sát → Rogan–Gladen | Floor | Quyết định |
|---|---:|---|---:|---:|---:|---:|---|---|---|
| `tone_ok` | 100 | 24 / 4 / 6 / 66 | 0.757 | 0.857 | 0.800 | 0.943 | 0.280 → 0.300 | Đạt | Dùng được cho tiêu chí tone đã hiệu chuẩn; tiếp tục audit nhãn. |
| `helpful` | 100 | 9 / 0 / 21 / 70 | 0.375 | 1.000 | 0.300 | 1.000 | 0.090 → 0.300 | Không đạt κ, recall | Không dùng làm gate; nó bỏ sót phần lớn câu trả lời sai tiền. |

Số liệu từ `judge_tone_public.csv` và `judge_helpful_public.csv`; specificity = TN/(TN+FP). Rogan–Gladen dùng sensitivity = recall và specificity của từng judge. `helpful` có fail rate quan sát 9% trong khi tỉ lệ đã hiệu chỉnh là 30%, phù hợp với 21 false negative.

## Audit thủ công các bất đồng

| Judge | Case | Judge | Người | Kết luận khi đọc case | Hành động với rubric/nhãn |
|---|---|---|---|---|---|
| tone | H-008 | PASS | FAIL | Người đúng: “em”, “nha” quá suồng sã trong ngữ cảnh chăm sóc khách hàng. | Thêm điều kiện xưng hô lịch sự; không xem từ “Dạ” đơn lẻ là đủ. |
| tone | H-017 | PASS | FAIL | Người đúng: “bạn” không phù hợp khi đang xưng hô với khách lớn tuổi. | Nêu rõ cách xưng hô theo ngữ cảnh tuổi/quan hệ. |
| tone | H-029 | PASS | FAIL | Người đúng: “không cần nhắn thêm” mang giọng ra lệnh. | Rubric phải bắt câu mệnh lệnh dù câu mở đầu có “Dạ”. |
| tone | H-042 | FAIL | PASS | Người đúng: nội dung ngắn, lịch sự, có số tiền và thời gian nhận tiền; không cần ép xin lỗi. | Bỏ yêu cầu xin lỗi bắt buộc khi câu trả lời đã đủ ý. |
| tone | H-051 | FAIL | PASS | Người đúng: “refund” được CS LogiX cho phép; từ tiếng Anh này tự nó không làm câu thiếu lịch sự. | Liệt kê cách diễn đạt tiếng Anh được chấp nhận. |
| tone | H-063 | PASS | FAIL | Người đúng: hứa “sẽ hoàn thêm” vượt quá kết quả hệ thống. | Cấm hứa giao dịch chưa được xác nhận; đây là lỗi nội dung/an toàn, không chỉ tone. |
| tone | H-081 | FAIL | PASS | Judge đúng theo ghi chú của CSV: người gắn nhãn đã đọc nhầm ticket; câu từ chối khớp policy. | Sửa nhãn người trước khi dùng làm chuẩn vàng; ghi lại lý do sửa. |
| helpful | HL-015 | PASS | FAIL | Người đúng: reply báo 55.000 VND nhưng ghi chú ledger là 40.000 VND. | Đưa đối chiếu số tiền/ledger vào tiêu chí helpful; gate tiền bằng grader code. |
| helpful | HL-016 | PASS | FAIL | Người đúng: lời xin lỗi dài không khắc phục số tiền 55.000 VND sai so với ledger 35.000 VND. | Không để văn phong dài/lịch sự che lỗi factual. |
| helpful | HL-020 | PASS | FAIL | Người đúng: reply báo 90.000 VND trong khi ledger ghi 120.000 VND. | Bắt buộc kiểm tra câu trả lời với nguồn sự thật. |
| helpful | HL-043 | PASS | FAIL | Người đúng: reply báo 35.000 VND nhưng ledger ghi 20.000 VND. | Dùng so sánh số có cấu trúc; không giao kiểm tiền cho judge ngôn ngữ. |
| helpful | HL-047 | PASS | FAIL | Người đúng: “Ok bạn” sai xưng hô trong trường hợp này và thiếu thông tin xử lý hữu ích. | Thêm kiểm tra xưng hô phù hợp và mức thông tin tối thiểu. |

## Kết luận

- `tone_ok` qua cả ba floor. Bất đồng cho thấy rubric cần phân biệt giọng lịch sự với độ dài, lời xin lỗi và từ “refund”; judge vẫn cần lấy mẫu audit định kỳ.
- `helpful` không đủ recall (0.300) và κ (0.375). Nó chấp nhận các câu rất trôi chảy nhưng sai tiền, vì vậy không được dùng làm cổng merge. Số tiền và phê duyệt tiếp tục được kiểm bằng code.
- Cả hai CSV đều là replay công khai, không phải held-out đánh giá judge mới. Nhãn sai như H-081 cần được sửa và audit bằng người độc lập trước khi coi là ground truth.
