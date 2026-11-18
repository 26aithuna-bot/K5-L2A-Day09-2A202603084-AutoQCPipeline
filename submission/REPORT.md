# Báo cáo Day 09 — Nguyễn Anh Thư, 2A202603084

## 1. Kết luận trước
Pipeline nhận 193/224 ảnh (31 ảnh bị loại ở intake), kết luận **Hold**. Dataset nháp có 193 ảnh, không còn lỗi bắt buộc; còn 34/193 ảnh có cảnh báo chưa xử lý hết (17.62%, ngưỡng Hold là 10%). `clean_v1` chỉ là bản nháp, chưa được phát hành.

## 2. Lỗi và phân việc
Số dưới đây là số issue trong `02_error_list_v1.csv`; các lỗi intake đã được tính trong cùng báo cáo.

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| BAD_SIZE / CORRUPT_IMAGE | 3 / 2 | Máy | Loại ảnh không đạt kích thước / không đọc được ở intake. |
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR / LEAK_TEST | 8 / 7 / 11 | Máy | Loại ảnh trùng hoặc trùng kho test/val để tránh dữ liệu rò rỉ. |
| BAD_CLASS_ID / BAD_FORMAT / BOX_ZERO / DUP_BOX | 6 / 3 / 4 / 7 | Máy | Xóa dòng nhãn không hợp lệ hoặc lặp; các dòng được ghi vào `03_fixes.csv`. |
| BOX_OUT_OF_IMAGE / BAD_CLASS_NAME | 8 / 2 | Máy | Cắt box về ảnh; chuẩn hóa `names` trong `data.yaml`. |
| MISSING_LABEL_FILE | 6 | Người | Máy không tự bịa nhãn; cần người gán. |
| Cảnh báo: BOX_HUGE / BOX_TINY / CLASS_RARE / EMPTY_LABEL | 3 / 6 / 4 / 11 | Người | Cảnh báo cần kiểm tra ngữ nghĩa hoặc ngữ cảnh ảnh. |
| Cảnh báo: POSSIBLE_FALSE_POS / POSSIBLE_LOOSE_BOX / POSSIBLE_MISSING / POSSIBLE_WRONG_CLASS | 28 / 27 / 53 / 17 | Người | Model chỉ nêu ý kiến, không tự sửa nhãn. |

Máy ghi 35 thay đổi: 20 dòng bị xóa, 8 box được cắt, 6 ảnh chuyển người gán nhãn và 1 lần sửa danh sách lớp. Hàng đợi có 121 ảnh; `img_0020` đứng đầu (priority 11.524) vì cộng dồn cờ thiếu box, sai lớp và dòng bị máy xóa. Sáu ảnh `NEEDS_LABEL` tiếp theo có priority 10. Với ngân sách 80, mô phỏng đã duyệt 80 ảnh; 74 ảnh có ít nhất một cờ ngữ nghĩa, tổng cộng 88 cờ POSSIBLE_* (một ảnh có thể có nhiều cờ). Đây là mô phỏng, không phải xác nhận của người gán nhãn thật.

Kiểm tra trực quan 10 ảnh đầu hàng đợi cũng cho thấy các ca cần người: `img_0031` có xe buýt nhưng thiếu file nhãn; `img_0126` có nhiều người nhưng thiếu file nhãn; `img_0170` có người chơi thể thao nhưng thiếu file nhãn. Các ảnh này đều có mã `MISSING_LABEL_FILE`.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 16 | `DUP_IMAGE_NEAR`: 1.00/0.50 → 1.00/0.83; `DUP_IMAGE_EXACT` giữ 1.00/1.00 | Bắt thêm ảnh gần trùng mà sweep chưa ghi nhận FP ở mức 16; không chọn 20 vì precision của exact giảm còn 0.33. |
| `second_opinion.conf` | 0.25 | 0.6 | `WRONG_CLASS`: .56/.83 → .62/.83; `MISSING`: .50/1.00 → .57/1.00; `LOOSE_BOX`: .29/.40 → .20/.20; `FALSE_POS`: .31/1.00 → .31/1.00 | 0.6 cải thiện precision cho hai loại cảnh báo chính mà không giảm recall của chúng; chấp nhận bỏ sót nhiều box lỏng hơn. Hàng đợi thực tế vẫn vượt ngân sách, nên ngưỡng này không đảm bảo Release. |

Calib chỉ có 39 ảnh: ở ngưỡng 16, `DUP_IMAGE_NEAR` vẫn bỏ sót 1/6 ảnh trùng gần; một ca làm recall đổi 16.7 điểm phần trăm. Trên raw còn có 7 cờ `DUP_IMAGE_NEAR`/224 ảnh; kết quả sweep không chứng minh mọi cặp đó đều là trùng thật, nên cần xem từng cặp trước khi loại.

## 4. Cửa chặn và điểm mù
(a) Chạy với `--budget 0 --reports work/rep_nb --export-dir work/exp_nb` cho kết luận **Rework**, mã thoát **20**; 6 ảnh thiếu nhãn vẫn không có file nhãn và `work/exp_nb/clean_v1` không được tạo. Điều này xác nhận lỗi bắt buộc không bị che bởi việc duyệt và không xuất dataset khi Rework.

(b) Điểm mù có bằng chứng: (1) ở `second_opinion.conf=0.6`, recall của `POSSIBLE_LOOSE_BOX` chỉ 0.20 trên calib; model có thể không cảnh báo nhiều box lỏng. (2) `phash_dist=16` vẫn bỏ sót 1/6 ảnh trùng gần đã chèn; biến đổi/cắt ảnh mạnh hơn có thể còn khó phát hiện. (3) `min_area_px=600` bỏ qua dự đoán vật nhỏ; ảnh `img_0160` có nhiều xe tải rất nhỏ ở xa nhưng chỉ một số box được đánh dấu, nên cần kiểm thủ công.

## 5. Train: raw vs clean
Chưa chạy train Colab; phần train tùy chọn chưa thực hiện trong lượt làm này.

## 6. Quyết định và ghi chú AI
(a) Quyết định: **Hold**, chưa phát hành. Cần người xác minh và xử lý cảnh báo còn lại; với 193 ảnh, phải giảm xuống tối đa 19 ảnh còn cảnh báo (dưới 10%) rồi chạy lại pipeline.

(b) Có dùng AI hỗ trợ viết code:
- Prompt chính: triển khai bốn module theo docstring và test; chạy calibration, pipeline và kiểm tra báo cáo.
- Kiểm chứng: chạy 50 test tập trung, sau đó toàn bộ 79 test; chạy calibration và pipeline, kiểm tra đầu ra cùng thử nghiệm ngân sách 0.
- Một lỗi của AI: khởi tạo nhóm lỗi theo `defaultdict(set)` sai cấu trúc lồng; test autofix bắt lỗi, sau đó sửa và chạy lại thành công.
