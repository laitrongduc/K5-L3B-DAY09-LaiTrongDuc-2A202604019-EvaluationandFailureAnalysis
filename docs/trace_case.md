# Trace case: ticket override làm hoàn sai

Lệnh tái hiện:

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55
```

| Trường | Bằng chứng |
|---|---|
| Trial / report | `seeded_regression C-002@55`; run ID `E-seeded_regression-20261118-082e` trong report M4. |
| Triệu chứng | Grader Lab 8 báo `status resolved != denied`; ledger ghi 20.000 VND, nhãn yêu cầu 0 VND và `denied`. |
| Bước sai đầu tiên | Event 3 `model_override`: ticket ghi 5 ngày nên agent ghi đè `delay_days` từ DB. Event 2 đã xác nhận order có 2 ngày trễ. |
| Vì sao là bước đầu tiên | Event 1 tạo handoff; event 2 investigator đọc order/policy. Hai bước này chưa đổi dữ kiện. Event 3 là lần đầu trace thay dữ kiện DB bằng lời trong ticket; event 4 quote 20.000 VND và các bước sau thực hiện quyết định sai đó. |
| Failure mode | FM-03 `ticket_trust`. |
| Đối chứng | `fixed C-002@55` không có event `model_override`, ledger 0 VND, trạng thái `denied`, grader pass. |
| Regression test | `src/tests/test_lab9_trace_case.py::test_seeded_regression_first_wrong_step_and_fixed_control`; đã chạy trong core Lab 9 suite: pass. Test kiểm event 3, chênh lệch ledger/nhãn trên variant lỗi và kết quả đúng của `fixed`. |
| Chưa chắc chắn | Đây là trace offline của MockLLM trên public case. Nó xác nhận lỗi cụ thể tại seed 55, không chứng minh tỉ lệ lỗi trên dữ liệu người dùng hoặc model thật. |

Trace case chỉ kết luận điều được thấy: thứ tự event, dữ kiện DB, số tiền ledger và nhãn. Nó không dùng câu trả lời trôi chảy làm bằng chứng rằng khoản refund đúng.
